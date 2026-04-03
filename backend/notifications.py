import os
import httpx

async def send_slack_notification(message: str, pr_url: str = None, color: str = "#36a64f"):
    """Send a notification to Slack via Webhook."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    # Create attachment
    attachment = {
        "fallback": message,
        "color": color,
        "title": "🤖 AI GitOps Sentinel",
        "text": message,
        "footer": "GitOps Sentinel Agent",
    }
    
    if pr_url:
        attachment["actions"] = [
            {
                "type": "button",
                "text": "View Pull Request",
                "url": pr_url,
                "style": "primary"
            }
        ]

    payload = {"attachments": [attachment]}

    try:
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=payload)
    except Exception as e:
        print(f"[Slack] Notification failed: {e}")
