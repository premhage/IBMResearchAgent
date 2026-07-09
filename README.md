# ResearchAgent — IBM watsonx.ai × Granite

An AI-powered academic research assistant that runs **entirely on your machine** with a single `flask run`. Powered by **IBM Granite 3.3 8B Instruct** via watsonx.ai and **Exa** neural web search.

---

## Feature Map

| UI Panel | Backend route | Agent method |
|---|---|---|
| Research Chat (ReAct timeline) | `POST /api/chat` | `agent.query()` |
| Dashboard | `GET /api/dashboard` | `agent.dashboard_summary()` |
| Papers & Citation Manager | `GET /api/papers` + `POST /api/cite` | KB list + `_format_citation()` |
| Gap Analysis | `GET /api/gaps` | `agent.gap_analysis()` |
| Contradiction Detection | `GET /api/contradictions` | `agent.contradiction_detection()` |
| Hypothesis Generator | `POST /api/hypotheses` | `agent.generate_hypotheses()` |
| PDF Upload | `POST /api/upload` | `kb.add_paper()` |

---

## IBM watsonx Orchestrate — Node Mapping

```
┌──────────────────────────────────────────────────────┐
│  watsonx Orchestrate Flow                            │
│                                                      │
│  [File Upload Node]                                  │
│      ↓  PDF bytes                                    │
│  [ResearchAgent Skill Node]                          │
│      → kb.add_paper()  (ingest + embed)              │
│      → agent.query()   (ReAct loop)                  │
│      → agent.gap_analysis() / contradiction() etc.   │
│      ↓  structured JSON (steps, final_answer, cites) │
│  [Generative Prompt Node]                            │
│      → POST /api/chat  (this Flask app)              │
│      ↓  rendered ReAct trace + citations             │
│  [Present to User Node]                              │
│      → frontend React timeline + citation cards      │
└──────────────────────────────────────────────────────┘
```

To replicate in Orchestrate:
1. **File Upload node** → points to `/api/upload` (multipart form)
2. **Tool / Skill node** → maps to `/api/chat`, `/api/gaps`, etc.
3. **Generative Prompt node** → uses the `prompt` field built in `agent.py:_react_prompt()`
4. **Display node** → renders the `steps[]` array as the reasoning trace

---

## Quick Start

### 1. Clone / copy

```bash
cd research_agent
```

### 2. Create virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure API keys

```bash
cp .env.example .env
# Edit .env and fill in:
#   WATSONX_API_KEY      — IBM Cloud API key (IAM)
#   WATSONX_PROJECT_ID   — watsonx.ai project GUID
#   WATSONX_URL          — regional endpoint
#   EXA_API_KEY          — from exa.ai dashboard
```

#### Getting IBM Cloud / watsonx.ai credentials

1. Log in to [cloud.ibm.com](https://cloud.ibm.com)
2. **Manage → Access (IAM) → API keys** → Create key → copy value → `WATSONX_API_KEY`
3. Open [dataplatform.cloud.ibm.com](https://dataplatform.cloud.ibm.com)
4. Create or open a **watsonx.ai project**
5. **Manage → General → Project ID** → copy → `WATSONX_PROJECT_ID`
6. Choose the closest region URL:
   - Dallas:  `https://us-south.ml.cloud.ibm.com`
   - London:  `https://eu-gb.ml.cloud.ibm.com`
   - Frankfurt: `https://eu-de.ml.cloud.ibm.com`

#### Getting Exa API key

1. Sign up at [exa.ai](https://exa.ai)
2. Dashboard → API Keys → Create → copy → `EXA_API_KEY`

### 5. Run

```bash
# Development
python app.py

# Production (gunicorn)
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

Visit **http://localhost:5000**

---

## Uploading Your IRJET Paper (Test-Case Mode)

1. Open the **Research Chat** tab
2. Click **Browse Files** in the sidebar → select your IRJET rover navigation PDF
3. ✅ Check **"Mark as test-case paper"** before uploading
4. The paper is ingested, chunked, and embedded — it persists across restarts in `knowledge_base/index.json`
5. Ask: *"Summarise the key contributions of the uploaded rover navigation paper"*

---

## Customising Agent Behaviour

All agent settings live in [`config.py`](config.py) under `AGENT_INSTRUCTIONS`:

```python
AGENT_INSTRUCTIONS = {
    # Tone & identity
    "tone": "You are a rigorous academic research assistant...",

    # Domain (change to your field)
    "domain": "autonomous rover navigation and mobile robotics",
    "sub_topics": ["SLAM", "path planning", "sensor fusion", ...],

    # Citation style: "IEEE" or "IRJET"
    "citation_style": "IEEE",

    # ReAct reasoning depth (1–10)
    "react_max_steps": 6,

    # Confidence threshold for [LOW-CONFIDENCE] flagging
    "confidence_threshold": 0.65,

    # Safety rules (add/remove as needed)
    "safety_rules": [
        "NEVER fabricate citations...",
        "Always distinguish [KB]/[WEB] from [INFER]...",
        ...
    ],
}
```

No other files need to be touched.

---

## Project Structure

```
research_agent/
├── app.py                  Flask routes (API + HTML)
├── agent.py                ReAct agent (gap/contra/hypo/cite)
├── knowledge_base.py       PDF ingestion, chunking, retrieval
├── watsonx_client.py       IBM watsonx.ai SDK wrapper (Granite)
├── exa_client.py           Exa neural search wrapper
├── config.py               ← AGENT_INSTRUCTIONS + env config
├── requirements.txt
├── .env.example            Copy to .env and fill in keys
├── templates/
│   └── index.html          Single-page Jinja template
├── static/
│   ├── css/style.css       Dark/light theme, all component styles
│   └── js/app.js           Tab nav, chat, uploads, all panel logic
├── uploads/                PDF files saved here on upload
└── knowledge_base/
    └── index.json          Persistent paper index (auto-created)
```

---

## Production Deployment (Docker)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
```

```bash
docker build -t research-agent .
docker run -p 5000:5000 --env-file .env research-agent
```

---

## Mock / Offline Mode

If `WATSONX_API_KEY` or `EXA_API_KEY` are not set, the app runs in **mock mode**:
- `watsonx_client._mock_generate()` returns a labelled stub ReAct trace
- `exa_client._mock_search()` returns synthetic results
- All UI panels still render correctly — ideal for frontend development

The status indicator in the top-right of the navbar shows the current mode.

---

## Safety & Integrity Guarantees

| Rule | Enforcement |
|---|---|
| No fabricated citations | Agent prompt explicitly prohibits it; citations sourced only from KB or Exa |
| Source transparency | All claims tagged `[KB]`, `[WEB]`, or `[INFER]` |
| Low-confidence flagging | Claims below threshold marked `[LOW-CONFIDENCE]` |
| Contradiction surfacing | Both citations shown with severity badge |
| No hallucination on missing info | Prompt instructs "state insufficient evidence" |
