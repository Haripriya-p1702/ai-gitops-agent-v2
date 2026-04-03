"""
LangChain-powered GitOps Agent.

Analyses changed files in a PR, identifies misconfigurations,
generates fixed versions, and returns structured results.
"""
import os
import textwrap
from typing import Optional
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage


def _get_llm():
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model="gemini-1.5-pro",
            temperature=0,
            google_api_key=os.getenv("GEMINI_API_KEY"),
        )


SYSTEM_PROMPT = textwrap.dedent("""\
You are an expert DevOps and Platform Engineering AI assistant specialising in
Kubernetes, Docker, GitHub Actions, and Terraform.

Your job:
1. Review infrastructure/configuration files changed in a Pull Request.
2. Identify ALL misconfigurations, security risks, missing best-practices.
3. Produce a corrected version of the file.
4. Provide a clear, concise explanation for each change.

Output EXACTLY this JSON structure (no markdown, no extra text):
{
  "has_issues": true | false,
  "severity": "critical" | "high" | "medium" | "low" | "none",
  "issues": [
    { "line": <int or null>, "description": "<what is wrong>" }
  ],
  "summary": "<one-sentence summary of all issues>",
  "fixed_content": "<complete corrected file content as a string>",
  "changes_explanation": "<bullet-point list of every change made and why>"
}
""")


def analyse_file(
    filename: str,
    original_content: str,
    static_hints: list[str],
) -> dict:
    """
    Run the LLM agent on a single file and return structured analysis.
    """
    llm = _get_llm()

    hints_text = ""
    if static_hints:
        hints_text = "\n\nStatic analysis pre-detected these potential issues (investigate each):\n"
        hints_text += "\n".join(f"- {h}" for h in static_hints)

    human_msg = textwrap.dedent(f"""\
    File: {filename}
    {hints_text}

    --- BEGIN FILE CONTENT ---
    {original_content}
    --- END FILE CONTENT ---

    Analyse the file and return the JSON response now.
    """)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_msg),
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    # strip markdown code fences if the model adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    import json
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # graceful fallback
        result = {
            "has_issues": False,
            "severity": "none",
            "issues": [],
            "summary": "Could not parse AI response.",
            "fixed_content": original_content,
            "changes_explanation": raw,
        }

    return result


def analyse_pr_files(files: list[dict]) -> list[dict]:
    """
    Analyse multiple files from a PR.
    `files` is a list of dicts: { filename, content, static_hints }
    Returns a list of analysis results enriched with filename.
    """
    results = []
    for f in files:
        if not f.get("content"):
            continue
        analysis = analyse_file(
            filename=f["filename"],
            original_content=f["content"],
            static_hints=f.get("static_hints", []),
        )
        analysis["filename"] = f["filename"]
        results.append(analysis)
    return results
