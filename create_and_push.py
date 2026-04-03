import os
from github import Github
import subprocess

# PROJECT_ROOT = r'c:\Users\harip\.gemini\antigravity\scratch\ai-gitops-agent'
# Using current directory as we will run inside the root

TOKEN = "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"
REPO_NAME = "ai-gitops-agent-v2"

def main():
    print(f"Connecting to GitHub...")
    g = Github(TOKEN)
    user = g.get_user()
    
    # 1. Create Repository
    try:
        repo = user.create_repo(REPO_NAME, private=False)
        print(f"Successfully created repository: {repo.full_name}")
    except Exception as e:
        if "name already exists" in str(e).lower():
            print(f"Repository {REPO_NAME} already exists, will use existing.")
            repo = user.get_repo(REPO_NAME)
        else:
            print(f"Failed to create repo: {e}")
            return

    repo_url = repo.clone_url.replace("https://", f"https://{TOKEN}@")
    print(f"Repo URL: {repo.clone_url}")

    # 2. Git Automation
    try:
        # Check if already a git repo
        is_git = os.path.exists(".git")
        
        if not is_git:
            print("Initializing git...")
            subprocess.run(["git", "init"], check=True)
            subprocess.run(["git", "checkout", "-b", "main"], check=True)
        
        # Add all files
        print("Adding files...")
        subprocess.run(["git", "add", "."], check=True)
        
        # Write .gitignore if it doesn't exist
        if not os.path.exists(".gitignore"):
            with open(".gitignore", "w") as f:
                f.write("node_modules/\n")
                f.write("venv/\n")
                f.write("__pycache__/\n")
                f.write(".env\n")
            subprocess.run(["git", "add", ".gitignore"], check=True)

        # Commit
        print("Commiting...")
        subprocess.run(["git", "commit", "-m", "Initial commit: AI GitOps Agent"], check=False) # OK if nothing changed

        # Force push to main
        print(f"Pushing to {repo.clone_url}...")
        subprocess.run(["git", "remote", "remove", "origin"], check=False)
        subprocess.run(["git", "remote", "add", "origin", repo_url], check=True)
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"], check=True)
        
        print("\n" + "="*40)
        print(f"DONE! Your code is now live at: {repo.html_url}")
        print("="*40)

    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e}")

if __name__ == "__main__":
    main()
