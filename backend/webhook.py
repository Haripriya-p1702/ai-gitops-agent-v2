"""
GitHub webhook handler — processes push/PR events and triggers the AI agent.
"""
import os
import hashlib
import hmac
import datetime
from notifications import send_slack_notification
from parser import parse_files
from agent import analyze_and_fix
from github_api import create_fix_pr
from websocket_manager import WebSocketManager
import asyncio

# De-duplication cache
processed_commits = set()

async def handle_github_webhook(
    payload: dict,
    event_type: str,
    ws_manager: WebSocketManager,
    push_event_fn,
):
    """Process an incoming GitHub webhook payload."""
    repo_name = payload.get("repository", {}).get("full_name", "unknown/repo")
    
    # ── Commit De-duplication ───────────────────────────────────────────────
    if event_type == "push":
        after_sha = payload.get("after")
        if after_sha and after_sha != "0000000000000000000000000000000000000000":
            if after_sha in processed_commits:
                print(f"[Webhook] Skipping duplicate push: {after_sha}")
                return
            processed_commits.add(after_sha)
            if len(processed_commits) > 200:
                list(processed_commits).pop(0) # Keep cache manageable
    
    # ── Slack & Dashboard: Handle PR Merges ─────────────────────────────────────
    if event_type == "pull_request":
        action = payload.get("action")
        pr_data = payload.get("pull_request", {})
        print(f"[Webhook] Pull Request Event Received: {action}")

        if action == "closed" and pr_data.get("merged"):
            title = pr_data.get("title", "Unknown PR")
            url = pr_data.get("html_url", "")
            print(f"[Webhook] EXCELLENT: PR Merged detected for {title}")
            
            # 1. Send Success Event to Dashboard
            merged_ev = {
                "id": _make_id(),
                "type": "pr_merged",
                "repo": repo_name,
                "message": f"✅ PR Merged! Infrastructure healed: {title}",
                "timestamp": _now(),
                "status": "success",
            }
            push_event_fn(merged_ev)
            await ws_manager.send_event(merged_ev)

            # 2. Send Success Notification to Slack
            from notifications import send_slack_notification
            await send_slack_notification(f"✅ *PR Merged & Healed!* \n Repo: `{repo_name}` \n Fix: {title}", url, color="#2eb886")
            return

    if event_type != "push":
        return

    ref = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "") if ref else "unknown"

    # ── Security & Loop Prevention: Ignore our own fix branches ──────────────
    if branch.startswith("ai-gitops-fix/"):
        print(f"[Webhook] Skipping event on agent's own fix branch: {branch}")
        return

    # ── Handle Pushes (New Code) ──────────────────────────────────────────────
    commits = payload.get("commits", [])
    changed_files = []
    for commit in commits:
        changed_files.extend(commit.get("added", []))
        changed_files.extend(commit.get("modified", []))

    # Full-Stack Mode: Watch EVERYTHING (Python, JS, TXT, etc.)
    relevant = list(set(changed_files))

    if not relevant:
        return

    # Emit "analyzing" event
    analyzing_event = {
        "id": _make_id(),
        "type": "analyzing",
        "repo": repo_name,
        "branch": branch,
        "files": relevant,
        "message": f"🔍 Analyzing {len(relevant)} changed file(s) in {repo_name}",
        "timestamp": _now(),
        "status": "running",
    }
    push_event_fn(analyzing_event)
    await ws_manager.send_event(analyzing_event)

    # Pull file contents and parse
    try:
        parsed = await parse_files(repo_name, relevant, payload)
    except Exception as e:
        err_event = {**analyzing_event, "type": "error", "message": f"❌ Parse error: {e}", "status": "error"}
        push_event_fn(err_event)
        await ws_manager.send_event(err_event)
        return

    # ── Fetch Full Repo Context ──────────────────────────────────────────────
    token = os.getenv("GITHUB_TOKEN", "")
    from parser import fetch_repo_manifest
    repo_context = await fetch_repo_manifest(repo_name, branch, token)

    # Run AI analysis in parallel for performance
    tasks = [
        _process_file_analysis(file_info, repo_name, branch, ws_manager, push_event_fn, repo_context)
        for file_info in parsed
    ]
    results = await asyncio.gather(*tasks)

    # ── Single PR for ALL Fixes in this Push ──────────────────────────────────
    valid_fixes = [r for r in results if r and r.get("fix")]
    
    if valid_fixes and os.getenv("GITHUB_TOKEN") and os.getenv("DEMO_MODE") != "true":
        # Call the refactored create_fix_pr with all fixes at once
        pr_url = await create_fix_pr(repo_name, branch, valid_fixes)
        
        if pr_url:
            # Re-calculating actual changed files for the dashboard event
            # Note: create_fix_pr filters out files without content changes
            actually_changed = [f for f in valid_fixes if f["fix"]["fixed_content"] != f["file_info"].get("content")]
            changed_count = len(actually_changed) if actually_changed else len(valid_fixes)

            # Emit PR Created event for the whole push
            pr_event = {
                "id": _make_id(),
                "type": "pr_created",
                "repo": repo_name,
                "message": f"✅ Grouped Fix PR opened for {changed_count} file(s): {pr_url}",
                "pr_url": pr_url,
                "timestamp": _now(),
                "status": "pr_created",
            }
            push_event_fn(pr_event)
            await ws_manager.send_event(pr_event)

            # Update results with PR URL for notifications
            for f in valid_fixes:
                f["pr_url"] = pr_url

    # ── Single Slack Message for Multi-Fix Commit ───────────────────────────────
    if valid_fixes:
        pr_url = valid_fixes[0].get("pr_url")
        summary_msg = f"🚀 *AI GitOps Sentinel: {len(valid_fixes)} Fixes Proposed*\n"
        summary_msg += f"Repo: `{repo_name}`\n"
        if pr_url:
            summary_msg += f"PR: <{pr_url}|View Grouped PR>\n\n"
        
        for f in valid_fixes:
            summary_msg += f"• *{f['path']}*\n"
            summary_msg += f"  _{f.get('description', 'No description')}_\n"
        
        from notifications import send_slack_notification
        await send_slack_notification(summary_msg, color="#36a64f", pr_url=pr_url)


async def _process_file_analysis(file_info, repo_name, branch, ws_manager, push_event_fn, repo_context=None):
    """Analyze a single file with full repo context."""
    # 1. Emit Issue Detected
    issue_event = {
        "id": _make_id(),
        "type": "issue_detected",
        "repo": repo_name,
        "branch": branch,
        "file": file_info["path"],
        "severity": file_info.get("severity", "medium"),
        "message": f"⚠️ Issue detected in {file_info['path']}",
        "analysis": file_info.get("issues", []),
        "timestamp": _now(),
        "status": "detected",
    }
    push_event_fn(issue_event)
    await ws_manager.send_event(issue_event)

    # 2. Generate Fix via LLM Agent with Repo Context
    fix = await analyze_and_fix(file_info, repo_context)
    if not fix:
        return None

    fix_event = {
        "id": _make_id(),
        "type": "fix_generated",
        "repo": repo_name,
        "branch": branch,
        "file": file_info["path"],
        "message": f"🤖 Fix generated for {file_info['path']}",
        "fix_description": fix["description"],
        "diff": fix["diff"],
        "fixed_content": fix["fixed_content"],
        "timestamp": _now(),
        "status": "fix_ready",
    }
    push_event_fn(fix_event)
    await ws_manager.send_event(fix_event)

    # Return the fix data so it can be grouped into one PR
    return {
        "path": file_info["path"],
        "file_info": file_info,
        "fix": fix,
        "description": fix["description"]
    }


def _make_id():
    import uuid
    return str(uuid.uuid4())[:8]


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"
