"""
File parser — reads and validates Kubernetes YAMLs, Dockerfiles, and GH Actions workflows.
Returns structured file info with detected issues for the AI agent.
"""
import os
import re
import yaml
import httpx
from typing import Optional


KNOWN_ISSUES_PATTERNS = {
    "k8s": [
        {
            "id": "missing_resources",
            "pattern": lambda d: _missing_resource_limits(d),
            "description": "Container missing resource requests/limits",
            "severity": "high",
        },
        {
            "id": "latest_tag",
            "pattern": lambda d: _uses_latest_tag(d),
            "description": "Container image uses :latest tag (non-reproducible)",
            "severity": "medium",
        },
        {
            "id": "missing_liveness_probe",
            "pattern": lambda d: _missing_probe(d, "livenessProbe"),
            "description": "Deployment missing livenessProbe",
            "severity": "medium",
        },
        {
            "id": "privileged_container",
            "pattern": lambda d: _is_privileged(d),
            "description": "Container running in privileged mode (security risk)",
            "severity": "critical",
        },
        {
            "id": "missing_namespace",
            "pattern": lambda d: not d.get("metadata", {}).get("namespace"),
            "description": "Resource missing namespace specification",
            "severity": "low",
        },
        {
            "id": "hostpath_volume",
            "pattern": lambda d: _uses_hostpath(d),
            "description": "Pod uses hostPath volume (security risk)",
            "severity": "high",
        },
    ],
    "docker": [
        {
            "id": "root_user",
            "pattern": lambda c: "USER root" not in c and "USER " not in c,
            "description": "Dockerfile does not set a non-root USER",
            "severity": "high",
        },
        {
            "id": "no_healthcheck",
            "pattern": lambda c: "HEALTHCHECK" not in c,
            "description": "Dockerfile missing HEALTHCHECK instruction",
            "severity": "medium",
        },
        {
            "id": "latest_base",
            "pattern": lambda c: bool(re.search(r"FROM \S+:latest", c)),
            "description": "Dockerfile uses :latest base image",
            "severity": "medium",
        },
        {
            "id": "add_instead_of_copy",
            "pattern": lambda c: bool(re.search(r"^\s*ADD ", c, re.MULTILINE)),
            "description": "Use COPY instead of ADD for local files",
            "severity": "low",
        },
    ],
    "gha": [
        {
            "id": "unversioned_action",
            "pattern": lambda c: bool(re.search(r"uses: \S+@main|uses: \S+@master", c)),
            "description": "GitHub Action uses mutable branch ref instead of pinned SHA/tag",
            "severity": "high",
        },
        {
            "id": "plaintext_secret",
            "pattern": lambda c: bool(re.search(r"(password|secret|token)\s*[:=]\s*['\"][^$]", c, re.IGNORECASE)),
            "description": "Possible plaintext secret in workflow file",
            "severity": "critical",
        },
    ],
    "python": [
        {
            "id": "print_statement",
            "pattern": lambda c: bool(re.search(r"^\s*print\(", c, re.MULTILINE)),
            "description": "Uses print() instead of proper logging",
            "severity": "low",
        },
        {
            "id": "hardcoded_host_port",
            "pattern": lambda c: bool(re.search(r"host=['\"]0\.0\.0\.0['\"]|port=\d{5,}", c)),
            "description": "Possible hardcoded host/port or invalid port number",
            "severity": "medium",
        },
    ],
    "requirements": [
        {
            "id": "unpinned_dependency",
            "pattern": lambda c: any(line and "==" not in line and not line.startswith("#") for line in c.splitlines()),
            "description": "Dependency not pinned to a specific version",
            "severity": "medium",
        },
        {
            "id": "malformed_requirement",
            "pattern": lambda c: bool(re.search(r"^\.\.", c, re.MULTILINE)),
            "description": "Malformed requirement line (starts with ..)",
            "severity": "high",
        },
    ],
}


async def fetch_repo_manifest(repo_name: str, branch: str, token: str) -> list[str]:
    """Fetch a list of all files in the repository for context."""
    try:
        url = f"https://api.github.com/repos/{repo_name}/git/trees/{branch}?recursive=1"
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                tree = resp.json().get("tree", [])
                return [node["path"] for node in tree if node["type"] == "blob"]
    except Exception:
        pass
    return []


async def parse_files(repo_name: str, file_paths: list[str], payload: dict) -> list[dict]:
    """Fetch file contents from GitHub and run static checks in parallel."""
    import asyncio
    token = os.getenv("GITHUB_TOKEN", "")
    commit_sha = payload.get("after") or payload.get("head_commit", {}).get("id", "HEAD")

    tasks = [
        _fetch_and_parse_single(repo_name, path, commit_sha, token)
        for path in file_paths
    ]
    
    results = await asyncio.gather(*tasks)
    return [r for r in results if r]


async def _fetch_and_parse_single(repo_name: str, path: str, commit_sha: str, token: str) -> dict:
    """Helper to fetch and parse a single file."""
    content = ""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw"} if token else {}
    
    try:
        url = f"https://api.github.com/repos/{repo_name}/contents/{path}?ref={commit_sha}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                # If we used raw header, content is direct. If not, it's base64 in JSON.
                # Standard api returns JSON by default if we don't force raw.
                # Let's handle both.
                if "application/json" in resp.headers.get("content-type", ""):
                    import base64
                    data = resp.json()
                    content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
                else:
                    content = resp.text
    except Exception:
        pass

    file_type = _detect_file_type(path)
    issues = _check_issues(content, file_type) if content else []

    return {
        "path": path,
        "type": file_type,
        "content": content,
        "issues": issues,
        "severity": _max_severity(issues),
    }


def _detect_file_type(path: str) -> str:
    path_lower = path.lower()
    if "dockerfile" in path_lower:
        return "docker"
    if ".github/workflows" in path or path_lower.endswith((".yml", ".yaml")) and "workflow" in path_lower:
        return "gha"
    if path_lower.endswith(".py"):
        return "python"
    if path_lower.endswith(("requirements.txt", "requirements.in")):
        return "requirements"
    if path_lower.endswith((".yaml", ".yml")):
        return "k8s"
    return "unknown"


def _check_issues(content: str, file_type: str) -> list[dict]:
    issues = []
    patterns = KNOWN_ISSUES_PATTERNS.get(file_type, [])
    for p in patterns:
        try:
            if file_type == "k8s":
                docs = list(yaml.safe_load_all(content))
                for doc in docs:
                    if doc and p["pattern"](doc):
                        issues.append({"id": p["id"], "description": p["description"], "severity": p["severity"]})
                        break
            else:
                if p["pattern"](content):
                    issues.append({"id": p["id"], "description": p["description"], "severity": p["severity"]})
        except Exception:
            pass
    return issues


def _max_severity(issues: list[dict]) -> str:
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    if not issues:
        return "none"
    return max(issues, key=lambda i: order.get(i["severity"], 0))["severity"]


# ── K8s helpers ───────────────────────────────────────────────────────────────

def _missing_resource_limits(doc: dict) -> bool:
    try:
        containers = doc["spec"]["template"]["spec"]["containers"]
        for c in containers:
            if not c.get("resources", {}).get("limits"):
                return True
    except (KeyError, TypeError):
        pass
    return False


def _uses_latest_tag(doc: dict) -> bool:
    try:
        containers = doc["spec"]["template"]["spec"]["containers"]
        for c in containers:
            image = c.get("image", "")
            if image.endswith(":latest") or ":" not in image:
                return True
    except (KeyError, TypeError):
        pass
    return False


def _missing_probe(doc: dict, probe_name: str) -> bool:
    try:
        containers = doc["spec"]["template"]["spec"]["containers"]
        for c in containers:
            if not c.get(probe_name):
                return True
    except (KeyError, TypeError):
        pass
    return False


def _is_privileged(doc: dict) -> bool:
    try:
        containers = doc["spec"]["template"]["spec"]["containers"]
        for c in containers:
            if c.get("securityContext", {}).get("privileged"):
                return True
    except (KeyError, TypeError):
        pass
    return False


def _uses_hostpath(doc: dict) -> bool:
    try:
        volumes = doc["spec"]["template"]["spec"].get("volumes", [])
        for v in volumes:
            if "hostPath" in v:
                return True
    except (KeyError, TypeError):
        pass
    return False
