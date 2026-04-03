"""
Webhook route: receives GitHub PR events, triggers the AI agent pipeline.
"""
import hashlib, hmac, json, os, asyncio
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

router = APIRouter()


def verify_signature(payload: bytes, signature: str) -> bool:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return True   # skip verification in dev mode
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)


async def process_pr(repo_full_name: str, pr_number: int, request: Request):
    manager = request.app.state.manager

    await manager.broadcast({
        "type": "pr_received",
        "repo": repo_full_name,
        "pr_number": pr_number,
        "message": f"📥 PR #{pr_number} received — starting analysis...",
    })

    from agent.github_integration import get_pr_files, create_fix_pr
    from agent.gitops_agent import analyse_pr_files

    try:
        files = get_pr_files(repo_full_name, pr_number)
        if not files:
            await manager.broadcast({
                "type": "no_files",
                "repo": repo_full_name,
                "pr_number": pr_number,
                "message": f"ℹ️ PR #{pr_number} has no supported infra files.",
            })
            return

        await manager.broadcast({
            "type": "analysis_start",
            "repo": repo_full_name,
            "pr_number": pr_number,
            "files": [f["filename"] for f in files],
            "message": f"🔍 Analysing {len(files)} file(s)...",
        })

        analyses = analyse_pr_files(files)

        issues_found = [a for a in analyses if a.get("has_issues")]

        await manager.broadcast({
            "type": "analysis_complete",
            "repo": repo_full_name,
            "pr_number": pr_number,
            "analyses": analyses,
            "issues_count": len(issues_found),
            "message": f"✅ Analysis done — {len(issues_found)} file(s) with issues.",
        })

        if issues_found:
            fix_result = create_fix_pr(repo_full_name, pr_number, analyses)
            await manager.broadcast({
                "type": "fix_pr_created",
                "repo": repo_full_name,
                "pr_number": pr_number,
                "fix_pr_url": fix_result.get("fix_pr_url"),
                "files_fixed": fix_result.get("files_fixed", []),
                "message": f"🚀 Fix PR created: {fix_result.get('fix_pr_url')}",
            })
        else:
            await manager.broadcast({
                "type": "no_issues",
                "repo": repo_full_name,
                "pr_number": pr_number,
                "message": f"🎉 PR #{pr_number} — no issues found!",
            })

    except Exception as e:
        await manager.broadcast({
            "type": "error",
            "repo": repo_full_name,
            "pr_number": pr_number,
            "message": f"❌ Error processing PR #{pr_number}: {str(e)}",
        })


@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(payload, sig):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event", "")
    if event != "pull_request":
        return {"status": "ignored", "event": event}

    data = json.loads(payload)
    action = data.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": action}

    repo_full_name = data["repository"]["full_name"]
    pr_number = data["pull_request"]["number"]

    background_tasks.add_task(process_pr, repo_full_name, pr_number, request)
    return {"status": "accepted", "pr": pr_number}
