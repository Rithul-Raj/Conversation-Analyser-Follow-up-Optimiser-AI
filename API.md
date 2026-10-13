
# FollowUp AI — API Reference

**Base URL (local):** `http://localhost:8000`  
**Start server:** `uvicorn main:app --reload` (from `conversation_ai/` directory)  
**Auth:** None (add API key header before production)  
**CORS:** All origins allowed in this version  

> All request/response bodies are `application/json`.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Server health check |
| POST | `/analyze-conversation` | Analyse a sales conversation (AI) |
| POST | `/ask-conversation` | Ask a question about a conversation (AI) |
| GET | `/leads` | List all leads with interaction counts |
| GET | `/leads/due-today` | Leads scheduled for today (no AI) |
| GET | `/leads/{lead_id}/history` | Conversation history for a lead |
| POST | `/reminder-status` | Compute reminder status for a date (no AI) |
| POST | `/notifications/by-date` | Filter a lead list by scheduled date |
| POST | `/notifications/daily` | Filter a lead list to OVERDUE/TODAY/TOMORROW |
| POST | `/notifications/client` | Search a lead list by client name or ID |

---

## 1. GET /health

**No request body.**

**Response 200:**
```json
{
  "status": "ok",
  "service": "conversation-intelligence-ai"
}
```

---

## 2. POST /analyze-conversation

The core endpoint. Calls Gemini AI, saves the result to SQLite, and returns structured intelligence.

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
  "conversation_id": 14,
  "history_used": 2
}
```

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

**422 — AI returned invalid data after 2 retries:**
```json
{
  "detail": "The AI returned an unexpected response. Please try again."
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

---

## 3. POST /ask-conversation

Answer any free-form question about a conversation. Single Gemini call, plain-text response.

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

Same 422 / 429 / 500 shapes as `/analyze-conversation`.

---

## 4. GET /leads

Returns all leads that have at least one stored conversation.

**No request body.**

### Response 200

```json
[
  {
    "lead_id": "LEAD-001",
    "total_interactions": 3,
    "last_interaction": "2026-10-12T10:30:00+05:30"
  },
  {
    "lead_id": "LEAD-002",
    "total_interactions": 1,
    "last_interaction": "2026-10-10T14:00:00+05:30"
  }
]
```

---

## 5. GET /leads/due-today

Returns all leads whose **latest** scheduled follow-up date is today. Pure Python — no AI, instant response. Useful for daily dashboard.

> ⚠️ This endpoint must be defined **before** `/leads/{lead_id}/history` in the router so FastAPI does not interpret "due-today" as a `lead_id` path parameter.

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
      "scheduled_followup_date": "13 Oct 2026",
      "scheduled_followup_time": "11:00 AM",
      "motive_summary": "Client ready to finalize pricing.",
      "client_pain_points": [],
      "client_recommendations": []
    },
    "created_at": "2026-10-12T10:30:00+05:30"
  }
]
```

Returns `[]` if no leads are scheduled for today.

---

## 6. GET /leads/{lead_id}/history

Returns stored conversations for a lead, **newest first**.

### Query Params

| Param | Type | Default | Rules |
|---|---|---|---|
| `limit` | integer | 10 | Min 1, max 100 |

### Response 200

```json
[
  {
    "id": 14,
    "lead_id": "LEAD-001",
    "bde_id": "EMP-042",
    "conversation_text": "Called Priya Nair. She confirmed the follow-up for tomorrow at 11 AM.",
    "analysis": {
      "sales_stage": "NEGOTIATION",
      "priority": "HIGH",
      "recommended_action": "CALL_CLIENT",
      "conversation_mode": "PROFESSIONAL",
      "motive_summary": "Client is ready to finalize pricing.",
      "scheduled_followup_date": "13 Oct 2026",
      "scheduled_followup_time": "11:00 AM",
      "client_pain_points": [],
      "client_recommendations": ["Requested callback tomorrow at 11 AM"]
    },
    "created_at": "2026-10-12T10:30:00+05:30"
  },
  {
    "id": 7,
    "lead_id": "LEAD-001",
    "bde_id": "EMP-042",
    "conversation_text": "First call with Priya. She asked about integration.",
    "analysis": { "..." : "..." },
    "created_at": "2026-10-01T09:00:00+05:30"
  }
]
```

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

## 7. POST /reminder-status

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
  "days_remaining": 7,
  "reminder_message": "Follow up in 7 days — 20 Oct 2026 at 11:00 AM."
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

## 8–10. POST /notifications/by-date, /daily, /client

> ⚠️ **These endpoints require the caller to supply the full lead list.** They are stateless filters — they do not query the database directly. For a DB-backed "leads due today" query, use `GET /leads/due-today` instead.

### 8. POST /notifications/by-date

Filter leads by scheduled date (and optionally time).

**Request:**
```json
{
  "date": "13 Oct 2026",
  "time": "11:00 AM",
  "entries": [
    {
      "lead_id": "LEAD-001",
      "client_name": "Priya Nair",
      "client_id": "CLIENT-101",
      "scheduled_followup_date": "13 Oct 2026",
      "scheduled_followup_time": "11:00 AM"
    }
  ]
}
```

**Response 200:** List of matching entries, each enriched with a `reminder` block.

```json
[
  {
    "lead_id": "LEAD-001",
    "client_name": "Priya Nair",
    "client_id": "CLIENT-101",
    "scheduled_followup_date": "13 Oct 2026",
    "scheduled_followup_time": "11:00 AM",
    "reminder": {
      "status": "TODAY",
      "days_remaining": 0,
      "reminder_message": "Follow up today — 13 Oct 2026 at 11:00 AM."
    }
  }
]
```

### 9. POST /notifications/daily

Return entries with status `OVERDUE`, `TODAY`, or `TOMORROW`, sorted by urgency.

**Request:**
```json
{
  "entries": [ { "...": "..." } ]
}
```

**Response 200:** Same shape as above, sorted OVERDUE → TODAY → TOMORROW.

### 10. POST /notifications/client

Search entries by client name or client_id substring (case-insensitive).

**Request:**
```json
{
  "identifier": "priya",
  "entries": [ { "...": "..." } ]
}
```

**Response 200:** Matching entries enriched with reminder block.

---

## Error Reference (all endpoints)

| HTTP Code | When |
|---|---|
| 200 | Success |
| 404 | Lead not found in database |
| 422 | Invalid request body (field-level validation errors or empty ID) |
| 429 | Gemini API rate limit exceeded |
| 500 | Missing API key or unexpected server error |

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

## Setup for Backend Integration

### 1. Clone the repository
```
git clone https://github.com/Rithul-Raj/Conversation-Analyser-Follow-up-Optimiser-AI.git
cd Conversation-Analyser-Follow-up-Optimiser-AI
```

### 2. Create a virtual environment
```
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Linux/Mac
```

### 3. Install dependencies
```
pip install -r requirements.txt
```

### 4. Configure environment variables
Copy `.env.example` to `.env` and fill in your Gemini API key:
```
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash-lite        # optional — this is the default
```
Get a free API key at: https://aistudio.google.com/app/apikey

### 5. Run the API server
```
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Run the offline test suite (no API key needed)
```
pytest tests/ -v
```
Expected output: **43 passed**

---

## Notes for Backend Team

- **Lead ID normalisation** is automatic. `lead001`, `LEAD-001`, and `Lead_001` all resolve to `LEAD-001`. Send any format — the system handles it.
- **AI call time** is 3–8 seconds for `/analyze-conversation` and `/ask-conversation`. Plan your frontend loading states accordingly.
- **Database** is local SQLite at `data/conversations.db` (auto-created). For multi-instance deployment, switch to PostgreSQL by replacing `services/database.py` — all callers stay the same.
- **CORS** is `*` for development. Restrict to your frontend domain before production.
- **No authentication** in this version. Add an API key header or JWT before production deployment.
- **Scheduled date format** in DB is always `DD Mon YYYY` (e.g. `"13 Oct 2026"`). Use this format in date search queries.
