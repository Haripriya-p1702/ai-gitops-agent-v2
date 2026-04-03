"""
File parsers: extract meaningful content from K8s YAML, Dockerfiles,
GitHub Actions workflows, and Terraform files from a PR diff.
"""
import re
import yaml
from typing import Optional


SUPPORTED_EXTENSIONS = {
    "k8s":       [".yaml", ".yml"],
    "dockerfile": ["Dockerfile", ".dockerfile"],
    "actions":   [".github/workflows"],
    "terraform": [".tf"],
}


def classify_file(filename: str) -> str:
    """Return the category of a file based on its name/path."""
    fn = filename.lower()
    if ".github/workflows" in fn:
        return "github_actions"
    if fn.endswith(".tf"):
        return "terraform"
    if "dockerfile" in fn.split("/")[-1].lower():
        return "dockerfile"
    if fn.endswith((".yaml", ".yml")):
        return _classify_yaml(filename)
    return "unknown"


def _classify_yaml(filename: str) -> str:
    """Attempt to distinguish K8s manifests from other YAML."""
    k8s_keywords = [
        "deployment", "service", "ingress", "configmap", "secret",
        "statefulset", "daemonset", "hpa", "pvc", "pod", "rbac",
        "clusterrole", "rolebinding", "namespace", "cronjob",
    ]
    fn_lower = filename.lower()
    if any(k in fn_lower for k in k8s_keywords):
        return "kubernetes"
    if "values" in fn_lower or "chart" in fn_lower or "helm" in fn_lower:
        return "helm"
    if ".github" in fn_lower:
        return "github_actions"
    # default — treat as generic YAML / possible K8s
    return "kubernetes"


def extract_issues_hint(filename: str, content: str) -> list[str]:
    """
    Quick static checks that help the LLM focus.
    Returns a list of plain-English hints about potential problems.
    """
    hints = []
    category = classify_file(filename)

    if category in ("kubernetes", "helm"):
        hints += _k8s_hints(content)
    elif category == "dockerfile":
        hints += _dockerfile_hints(content)
    elif category == "github_actions":
        hints += _actions_hints(content)
    elif category == "terraform":
        hints += _terraform_hints(content)

    return hints


# ── K8s static checks ────────────────────────────────────────────────────────
def _k8s_hints(content: str) -> list[str]:
    hints = []
    try:
        docs = list(yaml.safe_load_all(content))
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind", "")
        spec = doc.get("spec", {}) or {}
        template = spec.get("template", {}) or {}
        pod_spec = template.get("spec", {}) or {}
        containers = pod_spec.get("containers", []) or []

        for c in containers:
            name = c.get("name", "<unnamed>")
            image = c.get("image", "")
            # latest tag
            if image.endswith(":latest") or (":" not in image):
                hints.append(f"Container '{name}' uses ':latest' tag — pin to a specific version.")
            # missing resource limits
            resources = c.get("resources", {}) or {}
            if not resources.get("limits"):
                hints.append(f"Container '{name}' has no resource limits (CPU/memory).")
            if not resources.get("requests"):
                hints.append(f"Container '{name}' has no resource requests.")
            # running as root
            sc = c.get("securityContext", {}) or {}
            if sc.get("runAsRoot") is True or sc.get("runAsUser") == 0:
                hints.append(f"Container '{name}' is configured to run as root.")
            # missing liveness / readiness probes
            if not c.get("livenessProbe"):
                hints.append(f"Container '{name}' has no livenessProbe.")
            if not c.get("readinessProbe"):
                hints.append(f"Container '{name}' has no readinessProbe.")

        # missing namespace
        metadata = doc.get("metadata", {}) or {}
        if kind in ("Deployment", "Service", "StatefulSet") and not metadata.get("namespace"):
            hints.append(f"{kind} '{metadata.get('name', '?')}' has no namespace set.")

    return hints


# ── Dockerfile static checks ─────────────────────────────────────────────────
def _dockerfile_hints(content: str) -> list[str]:
    hints = []
    lines = content.splitlines()
    from_lines = [l for l in lines if l.strip().upper().startswith("FROM")]
    for fl in from_lines:
        if ":latest" in fl or (len(fl.split()) >= 2 and ":" not in fl.split()[1]):
            hints.append(f"Dockerfile uses ':latest' base image: `{fl.strip()}`")
    if not any("USER" in l.upper() for l in lines):
        hints.append("Dockerfile does not set a non-root USER — runs as root by default.")
    if not any("HEALTHCHECK" in l.upper() for l in lines):
        hints.append("Dockerfile has no HEALTHCHECK instruction.")
    # ADD vs COPY
    if any(l.strip().upper().startswith("ADD ") for l in lines):
        hints.append("Use COPY instead of ADD unless you need URL fetch or tar extraction.")
    return hints


# ── GitHub Actions static checks ────────────────────────────────────────────
def _actions_hints(content: str) -> list[str]:
    hints = []
    try:
        workflow = yaml.safe_load(content) or {}
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    jobs = workflow.get("jobs", {}) or {}
    for job_id, job in jobs.items():
        steps = job.get("steps", []) or []
        for step in steps:
            uses = step.get("uses", "")
            # pinned to @vX vs @sha
            if uses and "@" in uses:
                ref = uses.split("@")[-1]
                if not re.match(r"[0-9a-f]{40}", ref) and not ref.startswith("v"):
                    hints.append(f"Action `{uses}` is not pinned to a SHA or version tag.")
            # secrets in run scripts
            run = step.get("run", "")
            if run and re.search(r'echo\s+\$\{\{.*secrets', run):
                hints.append("Potential secret leak: echoing a secret in a run step.")

    # missing permissions block
    if "permissions" not in workflow:
        hints.append("Workflow has no top-level `permissions` block — uses default (write-all).")

    return hints


# ── Terraform static checks ──────────────────────────────────────────────────
def _terraform_hints(content: str) -> list[str]:
    hints = []
    if re.search(r'access_key\s*=\s*"[^"]{5,}"', content):
        hints.append("Possible hardcoded AWS access_key in Terraform file.")
    if re.search(r'secret_key\s*=\s*"[^"]{5,}"', content):
        hints.append("Possible hardcoded AWS secret_key in Terraform file.")
    if not re.search(r'backend\s+"', content) and "terraform" in content:
        hints.append("No remote backend configured — state will be stored locally.")
    return hints
