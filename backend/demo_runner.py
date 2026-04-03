"""
Demo Runner — simulates realistic webhook events for hackathon demos.
Cycles through various scenarios: K8s issues, Dockerfile problems, GH Actions misconfigs.
"""
import asyncio
import uuid
import datetime
from typing import Callable
from websocket_manager import WebSocketManager


DEMO_SCENARIOS = [
    {
        "repo": "Haripriya-p1702/gitops-sentinel-demo-k8s-",
        "branch": "main",
        "file": "deployment.yaml",
        "type": "k8s",
        "issues": [
            {"id": "latest_tag", "description": "Container image uses :latest tag (non-reproducible)", "severity": "medium"},
            {"id": "missing_resources", "description": "Container missing resource requests/limits", "severity": "high"},
            {"id": "missing_liveness_probe", "description": "Deployment missing livenessProbe", "severity": "medium"},
        ],
        "fix_description": "Pinned image to nginx:1.27.0, added resource limits (CPU: 500m, Memory: 256Mi), added livenessProbe and readinessProbe.",
        "fixes_applied": [
            "Replaced nginx:latest → nginx:1.27.0",
            "Added resources.requests (cpu: 100m, memory: 128Mi)",
            "Added resources.limits (cpu: 500m, memory: 256Mi)",
            "Added livenessProbe with /healthz endpoint",
        ],
        "pr_url": "https://github.com/acme-corp/payment-service/pull/42",
        "severity": "high",
    },
    {
        "repo": "Haripriya-p1702/gitops-sentinel-demo-k8s-",
        "branch": "main",
        "file": "Dockerfile",
        "type": "docker",
        "issues": [
            {"id": "root_user", "description": "Dockerfile does not set a non-root USER", "severity": "high"},
            {"id": "latest_base", "description": "Dockerfile uses :latest base image", "severity": "medium"},
            {"id": "no_healthcheck", "description": "Dockerfile missing HEALTHCHECK instruction", "severity": "medium"},
        ],
        "fix_description": "Changed base to node:20-alpine, added USER node for security, added HEALTHCHECK, replaced ADD with COPY.",
        "fixes_applied": [
            "Changed FROM node:latest → FROM node:20-alpine",
            "Added USER node (non-root execution)",
            "Added HEALTHCHECK instruction",
            "Replaced ADD with COPY for local files",
        ],
        "pr_url": "https://github.com/acme-corp/auth-service/pull/17",
        "severity": "high",
    },
    {
        "repo": "Haripriya-p1702/gitops-sentinel-demo-ci-cd",
        "branch": "main",
        "file": ".github/workflows/deploy.yml",
        "type": "gha",
        "issues": [
            {"id": "unversioned_action", "description": "GitHub Action uses mutable branch ref instead of pinned SHA/tag", "severity": "high"},
            {"id": "plaintext_secret", "description": "Possible plaintext secret in workflow file", "severity": "critical"},
        ],
        "fix_description": "Pinned all GitHub Action refs to immutable version tags. Removed plaintext credential, replaced with GitHub Secret reference.",
        "fixes_applied": [
            "Pinned actions/checkout@main → actions/checkout@v4",
            "Pinned actions/setup-node@master → actions/setup-node@v4",
            "Replaced plaintext password with ${{ secrets.DB_PASSWORD }}",
        ],
        "pr_url": "https://github.com/acme-corp/infra-config/pull/8",
        "severity": "critical",
    },
    {
        "repo": "Haripriya-p1702/gitops-sentinel-demo-k8s-",
        "branch": "main",
        "file": "service.yaml",
        "type": "k8s",
        "issues": [
            {"id": "privileged_container", "description": "Container running in privileged mode (security risk)", "severity": "critical"},
            {"id": "hostpath_volume", "description": "Pod uses hostPath volume (security risk)", "severity": "high"},
        ],
        "fix_description": "Removed privileged mode and hostPath volume. Added proper securityContext with allowPrivilegeEscalation: false.",
        "fixes_applied": [
            "Set securityContext.privileged: false",
            "Replaced hostPath volume with emptyDir",
            "Added allowPrivilegeEscalation: false",
            "Added runAsNonRoot: true, runAsUser: 1000",
        ],
        "pr_url": "https://github.com/acme-corp/ml-service/pull/23",
        "severity": "critical",
    },
]


class DemoRunner:
    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager
        self._loop_running = False

    async def run_scenario(self, push_event_fn: Callable, scenario_index: int = None):
        """Run a single demo scenario."""
        import random
        scenario = DEMO_SCENARIOS[scenario_index % len(DEMO_SCENARIOS)] if scenario_index is not None \
            else random.choice(DEMO_SCENARIOS)
        await self._play_scenario(scenario, push_event_fn)

    async def run_loop(self, push_event_fn: Callable):
        """Run demo scenarios in a loop (one every 15 seconds)."""
        if self._loop_running:
            return
        self._loop_running = True
        idx = 0
        while self._loop_running:
            scenario = DEMO_SCENARIOS[idx % len(DEMO_SCENARIOS)]
            await self._play_scenario(scenario, push_event_fn)
            idx += 1
            await asyncio.sleep(18)

    async def _play_scenario(self, scenario: dict, push_event_fn: Callable):
        """Simulate the full event sequence for a scenario."""

        # 1. Push detected
        push_ev = {
            "id": _uid(),
            "type": "push_detected",
            "repo": scenario["repo"],
            "branch": scenario["branch"],
            "file": scenario["file"],
            "message": f"📥 Push detected in {scenario['repo']} → {scenario['file']}",
            "timestamp": _now(),
            "status": "running",
        }
        push_event_fn(push_ev)
        await self.ws_manager.send_event(push_ev)
        await asyncio.sleep(1.2)

        # 2. Analyzing
        analyzing_ev = {
            "id": _uid(),
            "type": "analyzing",
            "repo": scenario["repo"],
            "branch": scenario["branch"],
            "file": scenario["file"],
            "message": f"🔍 AI agent analyzing {scenario['file']}...",
            "timestamp": _now(),
            "status": "running",
        }
        push_event_fn(analyzing_ev)
        await self.ws_manager.send_event(analyzing_ev)
        await asyncio.sleep(2.5)

        # 3. Issue detected
        issue_ev = {
            "id": _uid(),
            "type": "issue_detected",
            "repo": scenario["repo"],
            "branch": scenario["branch"],
            "file": scenario["file"],
            "severity": scenario["severity"],
            "message": f"⚠️ Found {len(scenario['issues'])} issue(s) in {scenario['file']}",
            "analysis": scenario["issues"],
            "timestamp": _now(),
            "status": "detected",
        }
        push_event_fn(issue_ev)
        await self.ws_manager.send_event(issue_ev)
        await asyncio.sleep(2.0)

        # 4. Fix generated
        fix_ev = {
            "id": _uid(),
            "type": "fix_generated",
            "repo": scenario["repo"],
            "branch": scenario["branch"],
            "file": scenario["file"],
            "message": f"🤖 Fix generated for {scenario['file']}",
            "fix_description": scenario["fix_description"],
            "fixes_applied": scenario["fixes_applied"],
            "diff": _demo_diff(scenario),
            "timestamp": _now(),
            "status": "fix_ready",
        }
        push_event_fn(fix_ev)
        await self.ws_manager.send_event(fix_ev)
        await asyncio.sleep(1.5)

        # 5. PR created
        pr_ev = {
            "id": _uid(),
            "type": "pr_created",
            "repo": scenario["repo"],
            "branch": scenario["branch"],
            "file": scenario["file"],
            "pr_url": scenario["pr_url"],
            "message": f"✅ Fix PR opened automatically",
            "timestamp": _now(),
            "status": "pr_created",
        }
        push_event_fn(pr_ev)
        await self.ws_manager.send_event(pr_ev)


def _demo_diff(scenario: dict) -> str:
    if scenario["type"] == "k8s":
        return "\n".join([
            "--- a/k8s/deployment.yaml",
            "+++ b/k8s/deployment.yaml",
            "@@ -4,7 +4,8 @@",
            " metadata:",
            "   name: api-service",
            "+  namespace: production",
            " spec:",
            "   replicas: 2",
            "@@ -12,6 +13,14 @@",
            "       containers:",
            "       - name: api",
            "-        image: nginx:latest",
            "+        image: nginx:1.27.0",
            "         ports:",
            "         - containerPort: 80",
            "+        resources:",
            "+          requests:",
            "+            cpu: 100m",
            "+            memory: 128Mi",
            "+          limits:",
            "+            cpu: 500m",
            "+            memory: 256Mi",
            "+        livenessProbe:",
            "+          httpGet:",
            "+            path: /healthz",
            "+            port: 80"
        ])
    elif scenario["type"] == "docker":
        return "\n".join([
            "--- a/Dockerfile",
            "+++ b/Dockerfile",
            "-FROM node:latest",
            "+FROM node:20-alpine",
            " WORKDIR /app",
            "-ADD . .",
            "-RUN npm install",
            "+COPY package*.json ./",
            "+RUN npm ci --only=production",
            "+COPY . .",
            " EXPOSE 3000",
            "+HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:3000/health || exit 1",
            "+USER node",
            " CMD [\"node\", \"server.js\"]"
        ])
    else:
        return "\n".join([
            "--- a/.github/workflows/deploy.yml",
            "+++ b/.github/workflows/deploy.yml",
            "-      - uses: actions/checkout@main",
            "+      - uses: actions/checkout@v4",
            "-      - uses: actions/setup-node@master",
            "+      - uses: actions/setup-node@v4",
            "-        password: mysecretpassword123",
            "+        password: ${{ secrets.DB_PASSWORD }}"
        ])


def _uid():
    return str(uuid.uuid4())[:8]


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"
