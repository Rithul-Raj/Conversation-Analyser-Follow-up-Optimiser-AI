
# FollowUp AI — API Reference

**Base URL (local):** `http://localhost:8000`  
**Start server:** `uvicorn main:app --reload` (from the repo root directory)  
**Interactive Docs:** `http://localhost:8000/docs` (Swagger UI)  
**Auth:** None (add API key header before production)  
**CORS:** All origins allowed in this version  
**Database:** MongoDB (`followup_ai` database, `conversations` collection)

> All request/response bodies are `application/json`.

---

## Endpoints Overview

| # | Method | Path | Workflow | Description |
|---|---|---|---|---|
| 1 | GET | `/health` | — | Server & DB health check |
| 2 | POST | `/analyze-conversation` | **Workflow 1** | Analyse a conversation → save to MongoDB → return AI output |
| 3 | POST | `/ask-conversation` | **Workflow 2** | Ask a question using a provided conversation text |
| 4 | POST | `/ask-by-lead` | **Workflow 3** | Ask a question — history fetched from MongoDB by lead_id |
| 5 | GET | `/leads` | — | List all leads with interaction counts |
| 6 | GET | `/leads/due-today` | — | Leads scheduled for today + overdue leads |
| 7 | GET | `/leads/{lead_id}/history` | — | Full conversation history for a lead |
| 8 | POST | `/reminder-status` | — | Compute reminder status for any date (no AI) |
| 9 | POST | `/notifications/by-date` | — | Filter a lead list by scheduled date |
| 10 | POST | `/notifications/daily` | — | Filter a lead list to OVERDUE/TODAY/TOMORROW |
| 11 | POST | `/notifications/client` | — | Search a lead list by client name or ID |

---

## 1. GET /health

**No request body.**

**Response 200:**
```json
{
  "status": "ok",
  "service": "conversation-intelligence-ai",
  "db": "mongodb"
}
```

---

## 2. POST /analyze-conversation  *(Workflow 1)*

**The core endpoint.** Calls Gemini AI, saves the result to MongoDB, and returns structured intelligence.

- Past conversations for the same `lead_id` are automatically fetched from MongoDB and injected as context.
- Retries once if the LLM returns malformed JSON.
- Returns the MongoDB `conversation_id` (24-char hex string) of the saved document.

### Request

```json
{
  "lead_id": "LEAD-001",
  "bde_id": "EMP-042",
  "conversation_text": "Called Priya Nair, VP Procurement at TechCorp. She liked the product demo and is ready to proceed. She asked us to call her back in 2 weeks to finalize pricing. She specifically said to call at 11 AM on that day."
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `lead_id` | string | ✅ | Any alphanumeric ID. Auto-normalised: `lead001` → `LEAD-001`. Must have at least one alphanumeric char. |
| `bde_id` | string | ✅ | Same rules as `lead_id`. |
| `conversation_text` | string | ✅ | Min 20 chars. Must not be blank/whitespace-only. |

### Response 200

```json
{
  "sales_stage": "NEGOTIATION",
  "priority": "HIGH",
  "recommended_action": "CALL_CLIENT",
  "conversation_mode": "PROFESSIONAL",
  "motive_summary": "Client is ready to finalise pricing and wants a scheduled callback in two weeks.",
  "scheduled_followup_date": "27 Oct 2026",
  "scheduled_followup_time": "11:00 AM",
  "client_pain_points": [],
  "client_recommendations": ["Requested a callback in two weeks at 11 AM"],
  "follow_up_days": 1,
  "reminder": {
    "status": "UPCOMING",
    "days_remaining": 14,
    "reminder_message": "Follow up in 14 days — 27 Oct 2026 at 11:00 AM."
  },
  "lead_id": "LEAD-001",
  "bde_id": "EMP-042",
  "conversation_id": "6ad1d11ea39f47a14b11d60c",
  "history_used": 2
}
```

> **`conversation_id`** is a MongoDB ObjectId string (24 hex chars). Store this if you need to reference or link this specific conversation later.  
> **`history_used`** tells you how many past conversations from MongoDB were used as AI context.

**Enum values:**

| Field | Valid values |
|---|---|
| `sales_stage` | `AWARENESS`, `INTEREST`, `EVALUATION`, `NEGOTIATION`, `DECISION`, `CLOSED` |
| `priority` | `HIGH`, `MEDIUM`, `LOW` |
| `recommended_action` | `EXPLAIN_PRODUCT`, `SEND_QUOTATION`, `SEND_EMAIL`, `SCHEDULE_MEETING`, `SCHEDULE_DEMO`, `CALL_CLIENT`, `ANSWER_OBJECTION`, `SEND_DOCUMENTATION`, `FOLLOW_UP`, `ESCALATE_TECHNICAL`, `WAIT`, `CLOSE_LEAD` |
| `conversation_mode` | `PROFESSIONAL`, `CASUAL`, `TECHNICAL` |
| `reminder.status` | `OVERDUE`, `TODAY`, `TOMORROW`, `THIS_WEEK`, `UPCOMING`, `NOT_SCHEDULED` |

### Error Responses

**422 — Validation error (field-level):**
```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "conversation_text"],
      "msg": "String should have at least 20 characters",
      "input": "Too short",
      "ctx": {"min_length": 20}
    }
  ]
}
```

**422 — Empty normalized ID:**
```json
{
  "detail": "lead_id and bde_id must contain at least one alphanumeric character."
}
```

**429 — Rate limit:**
```json
{
  "detail": "The AI service rate limit has been reached. Please wait a moment and try again."
}
```

**500 — Missing API key:**
```json
{
  "detail": "Server configuration error: GEMINI_API_KEY is not set. Contact the server administrator."
}
```

**502 — AI failure (model error / bad response):**
```json
{
  "detail": "The AI service is temporarily unavailable. Please try again."
}
```

---

## 3. POST /ask-conversation  *(Workflow 2)*

**Follow-up Question — Case 1:** The frontend provides a conversation text and a question directly. The AI answers based on the provided context. No database read or write.

### Request

```json
{
  "conversation_text": "Client called asking about API rate limits and SLA guarantees. Mentioned they are also evaluating DataGuard. Very technical questions but avoided discussing decision timeline.",
  "question": "Is the client genuinely interested or benchmarking us?"
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `conversation_text` | string | ✅ | Min 20 chars, not blank |
| `question` | string | ✅ | Min 5 chars, not blank |

### Response 200

```json
{
  "answer": "The client appears to be benchmarking rather than genuinely evaluating. They asked very specific technical questions while avoiding any discussion of their internal decision timeline, and they mentioned DataGuard by name. This pattern is typical of procurement benchmarking where the decision may already be made."
}
```

### Error Responses

Same 422 / 429 / 500 / 502 shapes as `/analyze-conversation`.

---

## 4. POST /ask-by-lead  *(Workflow 3)*

**Follow-up Question — Case 2:** The frontend sends `lead_id`, `bde_id`, and a question. The backend fetches the full conversation history from MongoDB and passes it to the AI as context. No conversation text needs to be provided by the caller.

> Use this when the BDE wants to ask something based on the full history of all past interactions with a lead.

### Request

```json
{
  "lead_id": "LEAD-001",
  "bde_id": "EMP-042",
  "question": "What are the main pain points raised by this lead across all conversations?"
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `lead_id` | string | ✅ | Same normalisation as `/analyze-conversation` |
| `bde_id` | string | ✅ | Same normalisation as `/analyze-conversation` |
| `question` | string | ✅ | Min 5 chars, not blank |

### Response 200

```json
{
  "lead_id": "LEAD-001",
  "bde_id": "EMP-042",
  "question": "What are the main pain points raised by this lead across all conversations?",
  "answer": "Across all conversations with Priya Nair at TechCorp, the main pain points raised are slow CRM performance and ongoing data migration issues. The client has also highlighted the need for clear SLA guarantees before committing.",
  "conversations_used": 3
}
```

> **`conversations_used`** is the number of stored MongoDB conversations used as context for the answer.

### Error Responses

**404 — No history found:**
```json
{
  "detail": "No conversations found for lead 'LEAD-001'. Please run /analyze-conversation first to store a conversation."
}
```

**422, 429, 500, 502** — Same shapes as `/analyze-conversation`.

---

## 5. GET /leads

Returns all leads that have at least one stored conversation.

**No request body.**

### Response 200

```json
[
  {
    "lead_id": "LEAD-001",
    "total_interactions": 3,
    "last_interaction": "2026-10-16T07:31:12.025058+00:00"
  },
  {
    "lead_id": "LEAD-002",
    "total_interactions": 1,
    "last_interaction": "2026-10-10T14:00:00+00:00"
  }
]
```

---

## 6. GET /leads/due-today

Returns all leads whose **latest** scheduled follow-up date is today **or overdue**. Pure Python — no AI, instant. Ideal for a daily action dashboard.

**No request body. No query params.**

### Response 200

```json
[
  {
    "lead_id": "LEAD-001",
    "bde_id": "EMP-042",
    "analysis": {
      "sales_stage": "NEGOTIATION",
      "priority": "HIGH",
      "recommended_action": "CALL_CLIENT",
      "scheduled_followup_date": "16 Oct 2026",
      "scheduled_followup_time": "11:00 AM",
      "motive_summary": "Client ready to finalize pricing.",
      "client_pain_points": [],
      "client_recommendations": []
    },
    "created_at": "2026-10-15T10:30:00+00:00",
    "reminder": {
      "status": "TODAY",
      "days_remaining": 0,
      "reminder_message": "Follow up today — 16 Oct 2026 at 11:00 AM."
    }
  }
]
```

Returns `[]` if no leads are scheduled for today or overdue.

---

## 7. GET /leads/{lead_id}/history

Returns stored conversations for a lead, **newest first**.

### Query Params

| Param | Type | Default | Rules |
|---|---|---|---|
| `limit` | integer | 10 | Min 1, max 100 |

### Response 200

```json
[
  {
    "id": "6ad1d11ea39f47a14b11d60c",
    "lead_id": "LEAD-001",
    "bde_id": "EMP-042",
    "conversation_text": "Called Priya Nair. She confirmed the follow-up for tomorrow at 11 AM.",
    "analysis": {
      "sales_stage": "NEGOTIATION",
      "priority": "HIGH",
      "recommended_action": "CALL_CLIENT",
      "conversation_mode": "PROFESSIONAL",
      "motive_summary": "Client is ready to finalize pricing.",
      "scheduled_followup_date": "17 Oct 2026",
      "scheduled_followup_time": "11:00 AM",
      "client_pain_points": [],
      "client_recommendations": ["Requested callback tomorrow at 11 AM"]
    },
    "created_at": "2026-10-16T07:31:12.025058+00:00"
  }
]
```

> **`id`** is the MongoDB ObjectId string for this specific conversation document.

### Error Responses

**404:**
```json
{
  "detail": "No conversations found for lead 'LEAD-001'."
}
```

**422 (invalid limit):**
```json
{
  "detail": [
    {
      "type": "greater_than_equal",
      "loc": ["query", "limit"],
      "msg": "Input should be greater than or equal to 1",
      "input": 0
    }
  ]
}
```

---

## 8. POST /reminder-status

Compute reminder status for any date/time combination. Pure Python — no AI, no API cost.

### Request

```json
{
  "scheduled_followup_date": "20 Oct 2026",
  "scheduled_followup_time": "11:00 AM"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `scheduled_followup_date` | string or null | ✅ | `"DD Mon YYYY"` format or `null` |
| `scheduled_followup_time` | string | ✅ | `"11:00 AM"`, `"Not specified"`, `"Morning"`, etc. |

### Response 200

```json
{
  "status": "UPCOMING",
  "days_remaining": 4,
  "reminder_message": "Follow up in 4 days — 20 Oct 2026 at 11:00 AM."
}
```

| Status | Meaning |
|---|---|
| `OVERDUE` | Scheduled date already passed |
| `TODAY` | Follow-up is today |
| `TOMORROW` | Follow-up is tomorrow |
| `THIS_WEEK` | 2 to 7 days away |
| `UPCOMING` | More than 7 days away |
| `NOT_SCHEDULED` | `scheduled_followup_date` is null |

---

## 9–11. Notification Endpoints (Stateless Filters)

> ⚠️ **These endpoints require the caller to supply the full lead list in the request body.** They are stateless filters — they do not query MongoDB. For a DB-backed "leads due today" query, use `GET /leads/due-today` instead.

### 9. POST /notifications/by-date

Filter leads by scheduled date (and optionally time).

**Request:**
```json
{
  "date": "16 Oct 2026",
  "time": "11:00 AM",
  "entries": [
    {
      "client_name": "Priya Nair",
      "client_id": "CLIENT-101",
      "scheduled_followup_date": "16 Oct 2026",
      "scheduled_followup_time": "11:00 AM",
      "notes": "Follow up on pricing"
    }
  ]
}
```

**Response 200:** List of matching entries, each enriched with a `reminder` block.

```json
[
  {
    "client_name": "Priya Nair",
    "client_id": "CLIENT-101",
    "scheduled_followup_date": "16 Oct 2026",
    "scheduled_followup_time": "11:00 AM",
    "notes": "Follow up on pricing",
    "reminder": {
      "status": "TODAY",
      "days_remaining": 0,
      "reminder_message": "Follow up today — 16 Oct 2026 at 11:00 AM."
    }
  }
]
```

### 10. POST /notifications/daily

Return entries with status `OVERDUE`, `TODAY`, or `TOMORROW`, sorted by urgency.

**Request:**
```json
{
  "entries": [
    {
      "client_name": "Priya Nair",
      "scheduled_followup_date": "16 Oct 2026",
      "scheduled_followup_time": "11:00 AM"
    }
  ]
}
```

**Response 200:** Same shape as `/notifications/by-date`, sorted OVERDUE → TODAY → TOMORROW.

### 11. POST /notifications/client

Search entries by client name or `client_id` substring (case-insensitive).

**Request:**
```json
{
  "identifier": "priya",
  "entries": [
    {
      "client_name": "Priya Nair",
      "client_id": "CLIENT-101",
      "scheduled_followup_date": "16 Oct 2026",
      "scheduled_followup_time": "11:00 AM"
    }
  ]
}
```

**Response 200:** Matching entries enriched with reminder block. Returns `404` if nothing matches.

---

## Error Reference (all endpoints)

| HTTP Code | When |
|---|---|
| 200 | Success |
| 404 | Lead not found in MongoDB, or no matching notification entries |
| 422 | Invalid request body (field-level validation errors or empty normalized ID) |
| 429 | Gemini API rate limit exceeded |
| 500 | Missing API key or unexpected server error |
| 502 | AI service failure (model returned bad response or is temporarily unavailable) |

### 422 Shape — validation errors (list)
```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "field_name"],
      "msg": "String should have at least N characters",
      "input": "...",
      "ctx": {"min_length": 20}
    }
  ]
}
```

### 422 Shape — business rule errors (string)
```json
{
  "detail": "lead_id and bde_id must contain at least one alphanumeric character."
}
```

> The backend must handle **both** 422 shapes. Check `typeof detail`: if it is a list, it is a field validation error; if it is a string, it is a business rule rejection.

---

## Backend Integration — Setup Instructions

### Prerequisites
- Python 3.11+
- MongoDB running locally or a MongoDB Atlas connection URI
- A Gemini API key (free at https://aistudio.google.com/app/apikey)

### 1. Clone the repository
```
git clone https://github.com/Rithul-Raj/Conversation-Analyser-Follow-up-Optimiser-AI.git
cd Conversation-Analyser-Follow-up-Optimiser-AI
```

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
```
GEMINI_API_KEY=your_gemini_api_key_here

# MongoDB — local default shown; replace with Atlas URI for cloud
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=followup_ai

# Optional
GEMINI_MODEL=gemini-3.5-flash-lite
TIMEZONE=Asia/Kolkata
```

### 5. Start MongoDB
```bash
# Windows (MongoDB installed as a service — already running)
# If not running:
net start MongoDB

# Linux / Mac
mongod --dbpath /data/db
```

### 6. Run the API server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Server is ready when you see:
```
MongoDB initialised.
Uvicorn running on http://0.0.0.0:8000
```

### 7. Verify with health check
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","service":"conversation-intelligence-ai","db":"mongodb"}
```

### 8. Run the offline test suite (no API key needed)
```bash
pytest tests/ -v
```
Expected output: **51 passed**

---

## Notes for Backend Team

- **Lead ID normalisation** is automatic. `lead001`, `LEAD-001`, and `Lead_001` all resolve to `LEAD-001`. Send any format — the system handles it.

- **MongoDB `conversation_id`** in the `/analyze-conversation` response is a 24-character hex string (MongoDB ObjectId). It can be stored in your system to reference a specific conversation document.

- **Workflow order matters for Workflow 3:** `/ask-by-lead` fetches history from MongoDB. The lead must have at least one stored conversation (via `/analyze-conversation`) before calling this endpoint, otherwise a `404` is returned.

- **AI call time** is 3–8 seconds for `/analyze-conversation`, `/ask-conversation`, and `/ask-by-lead`. Plan your frontend loading states accordingly.

- **CORS** is `*` for development. Restrict to your frontend domain before production.

- **No authentication** in this version. Add an API key header or JWT before production deployment.

- **Scheduled date format** in the DB is always `DD Mon YYYY` (e.g. `"16 Oct 2026"`). Use this format in date search queries.

- **502 vs 500:** `502` means the AI service failed (retry is safe). `500` means a server-side config error (do not retry automatically).

- **MongoDB Atlas:** To use Atlas instead of local MongoDB, simply change `MONGO_URI` in `.env` to your Atlas connection string. No code changes required.
