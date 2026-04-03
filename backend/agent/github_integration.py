"""
GitHub integration helpers:
- Fetch PR changed files
- Get file content
- Create a fix branch + commit + open PR
"""
import os
import base64
from github import Github, GithubException
from parsers.file_parser import classify_file, extract_issues_hint

SUPPORTED_CATEGORIES = {
    "kubernetes", "helm", "dockerfile", "github_actions", "terraform"
}


def get_github_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set in environment")
    return Github(token)


def get_pr_files(repo_full_name: str, pr_number: int) -> list[dict]:
    """
    Fetch all changed files in a PR that belong to supported categories.
    Returns list of { filename, content, static_hints, category }.
    """
    g = get_github_client()
    repo = g.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)

    result = []
    for f in pr.get_files():
        category = classify_file(f.filename)
        if category not in SUPPORTED_CATEGORIES:
            continue
        if f.status == "removed":
            continue

        try:
            file_obj = repo.get_contents(f.filename, ref=pr.head.sha)
            content = base64.b64decode(file_obj.content).decode("utf-8", errors="replace")
        except GithubException:
            content = ""

        hints = extract_issues_hint(f.filename, content)
        result.append({
            "filename": f.filename,
            "content": content,
            "static_hints": hints,
            "category": category,
            "sha": file_obj.sha if content else None,
        })

    return result


def create_fix_pr(
    repo_full_name: str,
    source_pr_number: int,
    analyses: list[dict],
) -> dict:
    """
    For each file with issues, commit the fixed version to a new branch
    and open a PR against the original PR's head branch.
    Returns { fix_pr_url, fix_branch, files_fixed }.
    """
    g = get_github_client()
    repo = g.get_repo(repo_full_name)
    source_pr = repo.get_pull(source_pr_number)
    base_branch = source_pr.head.ref   # fix targets the feature branch itself
    base_sha = source_pr.head.sha

    fix_branch = f"gitops-agent/fix-pr-{source_pr_number}"

    # Create fix branch
    try:
        repo.create_git_ref(ref=f"refs/heads/{fix_branch}", sha=base_sha)
    except GithubException as e:
        if "already exists" in str(e):
            pass  # branch exists from a previous run, reuse it
        else:
            raise

    files_fixed = []
    for analysis in analyses:
        if not analysis.get("has_issues"):
            continue
        fixed_content = analysis.get("fixed_content", "")
        if not fixed_content:
            continue

        filename = analysis["filename"]
        try:
            existing = repo.get_contents(filename, ref=fix_branch)
            repo.update_file(
                path=filename,
                message=f"fix(gitops-agent): auto-fix {filename}",
                content=fixed_content,
                sha=existing.sha,
                branch=fix_branch,
            )
        except GithubException:
            repo.create_file(
                path=filename,
                message=f"fix(gitops-agent): auto-fix {filename}",
                content=fixed_content,
                branch=fix_branch,
            )
        files_fixed.append(filename)

    if not files_fixed:
        return {"fix_pr_url": None, "fix_branch": None, "files_fixed": []}

    # Build PR body
    body_lines = ["## 🤖 AI GitOps Agent — Automated Fix\n"]
    body_lines.append(f"Fixing issues found in PR #{source_pr_number}.\n")
    for analysis in analyses:
        if not analysis.get("has_issues"):
            continue
        body_lines.append(f"### `{analysis['filename']}`")
        body_lines.append(f"**Summary:** {analysis.get('summary', '')}\n")
        body_lines.append("**Changes made:**")
        body_lines.append(analysis.get("changes_explanation", ""))
        body_lines.append("")

    fix_pr = repo.create_pull(
        title=f"🤖 GitOps Agent: Auto-fix for PR #{source_pr_number}",
        body="\n".join(body_lines),
        head=fix_branch,
        base=base_branch,
    )

    return {
        "fix_pr_url": fix_pr.html_url,
        "fix_branch": fix_branch,
        "files_fixed": files_fixed,
        "fix_pr_number": fix_pr.number,
    }
