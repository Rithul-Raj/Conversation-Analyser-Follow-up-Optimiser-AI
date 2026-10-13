# FollowUp AI — Conversation Analyser & Follow-up Optimiser

An AI-powered system for B2B sales teams that analyses sales conversation summaries and returns structured, actionable intelligence: sales stage, priority, recommended next action, follow-up schedule, client pain points, and more.

---

## API Documentation

→ **[API.md](API.md)** — Full endpoint reference with sample request/response JSON for every endpoint, error shapes, and integration notes.

Swagger UI is also available at **http://localhost:8000/docs** when the server is running.

---

## Quick Start

### 1. Clone the repository
```
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

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

Required:
```
GEMINI_API_KEY=your_gemini_api_key_here
```

Optional:
```
GEMINI_MODEL=gemini-3.5-flash-lite   # default — change if you prefer another model
TIMEZONE=Asia/Kolkata                # default — set to your server's local timezone
```

Get a free Gemini API key at: https://aistudio.google.com/app/apikey

### 5. Run the API server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Or use the terminal interface (CLI)
```bash
python cli.py
```

---

## Run the Offline Test Suite

No API key needed. No server needed.

```bash
pytest tests/test_normalize.py tests/test_reminder.py tests/test_api.py -v
```

Expected output: **44 passed** (or similar).

The three live-server test scripts (`test_date_extraction.py`, `test_notifications.py`, `test_pain_points.py`) require a running server and a live Gemini API key. Run them manually:
```bash
uvicorn main:app --reload
python tests/test_notifications.py
```

---

## Project Structure

```
.                            # Repository root (no sub-folder to navigate into)
├── main.py                  # FastAPI backend
├── cli.py                   # Terminal interface
├── .env                     # Your config (create from .env.example)
├── .env.example             # Config template
├── requirements.txt         # Python dependencies
├── API.md                   # Complete API documentation for backend team
├── README.md                # This file
├── data/
│   └── conversations.db     # SQLite database (auto-created on first run)
├── services/
│   ├── llm_client.py        # Gemini API client (google-genai SDK)
│   ├── database.py          # SQLite read/write
│   ├── reminder_service.py  # Reminder status computation (pure Python)
│   ├── followup_rules.py    # Priority → days lookup (pure Python)
│   ├── notification_service.py
│   ├── toast_notifier.py    # Windows desktop notifications
│   └── utils.py             # ID / time / date normalisation + get_today()
├── schemas/
│   └── conversation_analysis.py  # Pydantic models and enums
├── prompts/
│   ├── analysis_prompt.py   # AI prompts for conversation analysis
│   └── qa_prompt.py         # AI prompt for Q&A
└── tests/
    ├── test_normalize.py    # Offline: ID, time, date normalisation
    ├── test_reminder.py     # Offline: reminder status computation
    ├── test_api.py          # Offline: all API endpoints (AI mocked)
    ├── test_date_extraction.py   # Live-server only
    ├── test_notifications.py     # Live-server only
    └── test_pain_points.py       # Live-server only
```

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| **`google-genai` SDK** (not `google-generativeai`) | `google-generativeai` is end-of-life (Nov 2025) |
| **Default model: `gemini-3.5-flash-lite`** | High free-tier quota, fast response time; configurable via `GEMINI_MODEL` |
| **Sync FastAPI endpoints for AI calls** | Prevents event-loop blocking during 3–8s Gemini latency |
| **Local SQLite** | Zero-config for development; replace with PostgreSQL for multi-user |
| **TIMEZONE env variable** | Server clocks are often UTC; without this, IST reminders are off by 5h30m |
| **All "today" calculations timezone-aware** | `get_today()` in `services/utils.py` reads `TIMEZONE` env var |
| **`/leads/due-today` returns OVERDUE too** | Overdue leads need immediate attention, not just today's scheduled ones |
| **HTTP 502 for AI failures** | Distinguishes "our server crashed" (500) from "AI service unreachable" (502) |
| **Swagger at `/docs`** | Backend team needs interactive reference |

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Your Google Gemini API key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini model to use for all AI calls |
| `TIMEZONE` | `Asia/Kolkata` | Timezone for "today" calculations. Use any IANA timezone string. |
