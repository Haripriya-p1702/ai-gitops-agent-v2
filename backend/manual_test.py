import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure we can import from the current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import analyze_and_fix
from github_api import create_fix_pr

load_dotenv()

async def main():
    # === CONFIGURATION ===
    # 1. Update this to your ACTUAL repo name from the screenshot
    REPO_NAME = "Haripriya-p1702/gitops-sentinel-demo-k8s-" 
    BASE_BRANCH = "main"
    
    # 2. Path to the buggy file you want to test
    # (Make sure this file exists in your repo)
    FILE_PATH = "deployment.yaml"
    
    # 3. Simulate detection (or provide real issues if you want)
    # The agent will reason about these
    file_info = {
        "path": FILE_PATH,
        "type": "k8s",
        "content": """apiVersion: apps/v1
kind: Deployment
metadata:
  name: insecure-app
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: web
        image: nginx:latest
""",
        "issues": [
            {"severity": "high", "description": "Uses :latest tag instead of pinned version"},
            {"severity": "medium", "description": "Missing resource limits and liveness probes"}
        ]
    }

    print(f"🔍 Starting Manual Trigger for {REPO_NAME}...")
    print(f"🛠️  Analyzing {FILE_PATH}...")

    # Ensure DEMO_MODE is false ONLY for this script to hit the LLM and GitHub
    # but we store it back to true in .env for your dashboard demo.
    os.environ["DEMO_MODE"] = "false"

    # Step 1: Run AI Reasoning & Fix Generation
    fix = await analyze_and_fix(file_info)

    if fix:
        print(f"🤖 AI REASONING: {fix['description']}")
        print(f"✅ FIXES APPLIED: {', '.join(fix['fixes_applied'])}")
        
        # Step 2: Push to GitHub and Create PR
        print(f"🚀 Pushing fix to GitHub and opening Pull Request...")
        pr_url = await create_fix_pr(REPO_NAME, BASE_BRANCH, file_info, fix)
        
        if pr_url:
            print("\n" + "="*50)
            print(f"🎉 SUCCESS! Automated PR Created:")
            print(f"🔗 {pr_url}")
            print("="*50)
        else:
            print("\n❌ PR Creation Failed. Please check:")
            print("1. Your GITHUB_TOKEN in .env is valid and has 'repo' permissions.")
            print("2. The REPO_NAME matches your GitHub repository exactly.")
    else:
        print("❌ Agent failed to generate a fix.")

if __name__ == "__main__":
    asyncio.run(main())
