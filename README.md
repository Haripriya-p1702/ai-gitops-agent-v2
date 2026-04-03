# 🤖 AI GitOps Agent

> Autonomous AI agent that reviews Pull Requests for infrastructure misconfigurations and **automatically raises fix PRs**.

**Hackathon: Agentic AI to Solve Real-Time Problems**

---

## 🎯 What It Does

1. GitHub sends a webhook when a PR is opened
2. The agent fetches changed **K8s manifests, Dockerfiles, GitHub Actions workflows, and Terraform files**
3. A **LangChain AI agent (Gemini/OpenAI)** analyses each file, identifies all issues, and generates fixed versions
4. The agent **automatically opens a corrective PR** with detailed explanations
5. A **real-time dashboard** streams every step via WebSocket

---

## 🏗️ Architecture

```
GitHub PR  ──webhook──▶  FastAPI Backend
                              │
                         File Parser  (static analysis hints)
                              │
                         LangChain Agent  (Gemini / OpenAI)
                              │
                         GitHub API  (create fix branch + PR)
                              │
                         WebSocket  ──▶  Live Dashboard (HTML/JS)
```

---

## 🚀 Quick Start

### 1. Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Copy .env.example to .env and fill in your keys
copy .env.example .env
```

Edit `.env`:
```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_WEBHOOK_SECRET=my_secret_here
GEMINI_API_KEY=AIzaxxxxxxxxxxxxxxxxxx
LLM_PROVIDER=gemini
```

Start the server:
```bash
uvicorn main:app --reload --port 8000
```

### 2. Frontend (no build needed)

Open `frontend/index.html` directly in your browser — or serve with:
```bash
python -m http.server 3000 --directory frontend
```

### 3. GitHub Webhook Configuration

In your GitHub repo → Settings → Webhooks → Add webhook:
- **Payload URL**: `https://your-server/api/webhook/github`  
  *(use [ngrok](https://ngrok.com) for local: `ngrok http 8000`)*
- **Content type**: `application/json`
- **Secret**: same as `GITHUB_WEBHOOK_SECRET`
- **Events**: ✅ Pull requests

### 4. Demo Mode (no GitHub needed)

Click **▶ Run Demo** in the dashboard — this simulates a broken PR with real AI analysis.

---

## 🔍 What Gets Detected

| File Type | Issues Detected |
|---|---|
| **Kubernetes YAML** | `:latest` image tags, missing resource limits, no liveness/readiness probes, running as root, missing namespace |
| **Dockerfile** | `:latest` base image, running as root, no HEALTHCHECK, `ADD` instead of `COPY` |
| **GitHub Actions** | Unpinned action versions, secret leaks in `run:` steps, no `permissions` block |
| **Terraform** | Hardcoded credentials, missing remote backend |

---

## 📁 Project Structure

```
ai-gitops-agent/
├── backend/
│   ├── main.py                    # FastAPI app + WebSocket manager
│   ├── requirements.txt
│   ├── .env.example
│   ├── agent/
│   │   ├── gitops_agent.py        # LangChain AI agent (Gemini/OpenAI)
│   │   └── github_integration.py  # GitHub API: fetch files, create fix PR
│   ├── parsers/
│   │   └── file_parser.py         # Static analysis for all file types
│   └── routes/
│       ├── webhook.py             # GitHub webhook endpoint
│       └── demo.py                # Demo trigger endpoint
└── frontend/
    ├── index.html                 # Dashboard UI
    ├── style.css                  # Premium dark-mode design
    └── app.js                     # WebSocket client + live UI logic
```

---

## 🔑 API Keys Needed

| Key | Where to get |
|---|---|
| `GITHUB_TOKEN` | GitHub → Settings → Developer Settings → Personal access tokens (needs `repo` scope) |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com) |
| `OPENAI_API_KEY` | [OpenAI Platform](https://platform.openai.com) (if using OpenAI) |

---

## 🏆 Hackathon Demo Flow

1. Start backend → Open dashboard
2. Click **▶ Run Demo** 
3. Watch live: files scanned → AI analysis → issues found → fix PR created
4. Show the auto-generated PR body with explanations

**Time to wow the judges: < 2 minutes** ✅
