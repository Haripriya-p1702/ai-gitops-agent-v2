"""
Demo route: simulate a full PR analysis pipeline without needing a real GitHub repo.
Useful for hackathon demos.
"""
import asyncio
import json
from fastapi import APIRouter, Request, BackgroundTasks

router = APIRouter()

DEMO_K8S = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend-api
  template:
    metadata:
      labels:
        app: backend-api
    spec:
      containers:
      - name: backend-api
        image: myrepo/backend:latest
        ports:
        - containerPort: 8080
"""

DEMO_DOCKERFILE = """\
FROM node:latest
WORKDIR /app
ADD . .
RUN npm install
EXPOSE 3000
CMD ["node", "server.js"]
"""

DEMO_GH_ACTIONS = """\
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy
        run: |
          echo ${{ secrets.DEPLOY_KEY }}
          ./deploy.sh
"""

DEMO_FILES = [
    {"filename": "k8s/deployment.yaml",    "content": DEMO_K8S,       "category": "kubernetes"},
    {"filename": "Dockerfile",             "content": DEMO_DOCKERFILE, "category": "dockerfile"},
    {"filename": ".github/workflows/deploy.yml", "content": DEMO_GH_ACTIONS, "category": "github_actions"},
]


async def run_demo(request: Request):
    manager = request.app.state.manager

    await manager.broadcast({
        "type": "pr_received",
        "repo": "demo-org/demo-repo",
        "pr_number": 42,
        "message": "📥 Demo PR #42 received — starting analysis...",
    })
    await asyncio.sleep(1)

    from parsers.file_parser import extract_issues_hint
    from agent.gitops_agent import analyse_pr_files

    files_with_hints = []
    for f in DEMO_FILES:
        hints = extract_issues_hint(f["filename"], f["content"])
        files_with_hints.append({**f, "static_hints": hints})

    await manager.broadcast({
        "type": "analysis_start",
        "repo": "demo-org/demo-repo",
        "pr_number": 42,
        "files": [f["filename"] for f in files_with_hints],
        "message": f"🔍 Analysing {len(files_with_hints)} file(s)...",
    })
    await asyncio.sleep(0.5)

    analyses = analyse_pr_files(files_with_hints)
    issues_found = [a for a in analyses if a.get("has_issues")]

    await manager.broadcast({
        "type": "analysis_complete",
        "repo": "demo-org/demo-repo",
        "pr_number": 42,
        "analyses": analyses,
        "issues_count": len(issues_found),
        "message": f"✅ Analysis complete — {len(issues_found)} file(s) with issues.",
    })
    await asyncio.sleep(0.5)

    if issues_found:
        await manager.broadcast({
            "type": "fix_pr_created",
            "repo": "demo-org/demo-repo",
            "pr_number": 42,
            "fix_pr_url": "https://github.com/demo-org/demo-repo/pull/43",
            "files_fixed": [a["filename"] for a in issues_found],
            "message": "🚀 Fix PR created: https://github.com/demo-org/demo-repo/pull/43",
        })


@router.post("/demo/trigger")
async def trigger_demo(request: Request, background_tasks: BackgroundTasks):
    """Trigger a simulated PR analysis — no GitHub token required."""
    background_tasks.add_task(run_demo, request)
    return {"status": "demo started"}
