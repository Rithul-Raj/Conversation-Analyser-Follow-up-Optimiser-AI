# FollowUp AI — Conversation Analyser & Follow-up Optimiser

An AI-powered system for B2B sales teams that analyses sales conversation summaries and returns structured, actionable intelligence: sales stage, priority, recommended next action, follow-up schedule, client pain points, and more. Backed by MongoDB for persistent conversation history.

---

## API Documentation

→ **[API.md](API.md)** — Full endpoint reference with sample request/response JSON for every endpoint, error shapes, MongoDB setup, and integration notes.

Swagger UI is available at **http://localhost:8000/docs** when the server is running.

---

## The 3 Workflows

| Workflow | Endpoint | Input | What Happens |
|---|---|---|---|
| **1 — New Conversation Analysis** | `POST /analyze-conversation` | `lead_id, bde_id, conversation_text` | AI analyses → saves to MongoDB → returns full structured response |
| **2 — Q&A (Direct)** | `POST /ask-conversation` | `conversation_text, question` | AI answers from the conversation text you provide — stateless |
| **3 — Q&A (By Lead ID)** | `POST /ask-by-lead` | `lead_id, bde_id, question` | Backend fetches history from MongoDB → AI answers using all past conversations |

---

## Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/Rithul-Raj/Conversation-Analyser-Follow-up-Optimiser-AI.git
cd Conversation-Analyser-Follow-up-Optimiser-AI
```

> ⚠️ The project files are in the repo root — there is **no** `conversation_ai/` sub-folder to navigate into.

### 2. Create a virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / Mac
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Start MongoDB

**Windows (installed as a service):**
```bash
net start MongoDB
# or it starts automatically on boot
```

**Linux / Mac:**
```bash
mongod --dbpath /data/db
```

**MongoDB Atlas (cloud):** Skip this step — just add your Atlas URI to `.env` below.

### 5. Configure environment variables

Copy `.env.example` to `.env`:
```bash
cp .env.example .env   # Linux/Mac
copy .env.example .env  # Windows
```

Fill in your values:
```
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# MongoDB (local default — replace with Atlas URI for cloud)
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=followup_ai

# Optional
GEMINI_MODEL=gemini-3.5-flash-lite
TIMEZONE=Asia/Kolkata
```

Get a free Gemini API key at: https://aistudio.google.com/app/apikey

### 6. Run the API server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
MongoDB initialised.
Uvicorn running on http://0.0.0.0:8000
```

### 7. Open Swagger UI
Go to **http://localhost:8000/docs** to explore and test all endpoints interactively.

---

## Run the Offline Test Suite

No API key needed. No MongoDB needed. No server needed.

```bash
pytest tests/ -v
```

Expected output: **51 passed**

---

## Project Structure

```
.                               # Repository root
├── main.py                     # FastAPI app — all endpoints
├── cli.py                      # Terminal interface (BDE tool)
├── .env                        # Your config (create from .env.example)
├── .env.example                # Config template
├── requirements.txt            # Python dependencies
├── API.md                      # Complete API reference for backend team
├── README.md                   # This file
├── services/
│   ├── llm_client.py           # Gemini API client (analyze + ask + ask_with_history)
│   ├── mongo_database.py       # MongoDB read/write (pymongo)
│   ├── reminder_service.py     # Reminder status computation (pure Python)
│   ├── followup_rules.py       # Priority → follow-up days lookup
│   ├── notification_service.py # Stateless lead filtering
│   ├── toast_notifier.py       # Windows desktop notifications
│   └── utils.py                # ID / time / date normalisation + get_today()
├── schemas/
│   └── conversation_analysis.py  # Pydantic models and enums
├── prompts/
│   ├── analysis_prompt.py      # AI prompts for conversation analysis
│   └── qa_prompt.py            # AI prompt for Q&A
└── tests/
    ├── test_normalize.py        # Offline: ID, time, date normalisation
    ├── test_reminder.py         # Offline: reminder status computation
    └── test_api.py              # Offline: all API endpoints (AI + DB mocked)
```

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| **`google-genai` SDK** (not `google-generativeai`) | `google-generativeai` is end-of-life (Nov 2025) |
| **Default model: `gemini-3.5-flash-lite`** | Confirmed working on free-tier API keys; configurable via `GEMINI_MODEL` |
| **MongoDB** (not SQLite) | Scalable, production-ready; team requirement; ObjectId used as `conversation_id` |
| **Sync FastAPI endpoints for AI calls** | Prevents event-loop blocking during 3–8s Gemini latency |
| **3 separate workflow endpoints** | Clean separation: Workflow 1 (analyse+save), 2 (stateless Q&A), 3 (history-aware Q&A) |
| **TIMEZONE env variable** | Server clocks are often UTC; without this, IST reminders are off by 5h30m |
| **HTTP 502 for AI failures** | Distinguishes "our server crashed" (500) from "AI service unreachable" (502) |
| **Swagger at `/docs`** | Backend team needs interactive reference |

---

## Environment Variables Reference

| Variable | Default | Required | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | *(none)* | ✅ | Your Google Gemini API key |
| `MONGO_URI` | `mongodb://localhost:27017` | ✅ | MongoDB connection URI |
| `MONGO_DB_NAME` | `followup_ai` | — | MongoDB database name |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | — | Gemini model to use for all AI calls |
| `TIMEZONE` | `Asia/Kolkata` | — | Timezone for "today" calculations (any IANA string) |
