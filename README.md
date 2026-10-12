# Conversation Intelligence AI

An AI-powered terminal tool for Business Development Executives (BDEs) to analyse sales conversations, track lead follow-ups, and query stored conversation history — all from a simple numbered menu.

---

## What it does

| Feature | Description |
|---|---|
| Analyse a conversation | Paste a conversation summary; AI extracts sales stage, priority, recommended action, follow-up date/time, client pain points, and key motives |
| Ask a question | Ask any free-form question about a conversation (paste it or load a stored lead's history) |
| Find leads by date | Search all stored leads scheduled for a specific date and optional time |
| Lead history | View all past conversations and AI analysis for any lead |
| List all leads | See every lead on record with conversation count and last contact date |

All conversation data and analysis results are saved automatically in a local SQLite database. Each new analysis for the same lead automatically uses its past conversations as context.

---

## Requirements

- Python 3.11 or higher
- A free Gemini API key from [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

---

## Setup

### 1. Install dependencies

Open a terminal, navigate to the `conversation_ai/` folder, and run:

```
pip install -r requirements.txt
```

### 2. Add your API key

Create a file named `.env` inside the `conversation_ai/` folder with this content:

```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash-lite
```

Replace `your_key_here` with the key you copied from Google AI Studio.

---

## Running the tool

From inside the `conversation_ai/` folder, run:

```
python cli.py
```

You will see the main menu:

```
============================================================
     Conversation Intelligence AI  -  BDE Terminal
============================================================

  1   Analyse a conversation
  2   Ask a question about a conversation
  3   Find leads scheduled on a specific date
  4   View conversation history for a lead
  5   List all leads
  0   Exit

Choose (0-5):
```

Type a number and press Enter.

---

## Menu guide

### 1 — Analyse a conversation

Enter the Lead ID, your BDE ID, then paste the conversation. Type `END` on a new line when done.

- If the Lead ID already exists, you will see a warning showing the last entry so you can confirm it is the right lead before continuing.
- The AI analyses the current conversation with full awareness of all past conversations for that lead.
- Result is saved automatically.

**Lead ID format:** Use any consistent format — the tool normalises it automatically.  
`LEAD001`, `lead-001`, `Lead_001` all resolve to the same stored record: `LEAD-001`.

Example output fields:
```
Sales Stage   : EVALUATION
Priority      : HIGH
Recommended   : SEND_DOCUMENTATION
Mode          : PROFESSIONAL
Follow-up in  : 1 day(s)
Sched. Date   : 28 Sep 2026
Sched. Time   : 11:00 AM
History Used  : 2 past conversation(s)
Saved as      : Conversation #7
```

---

### 2 — Ask a question about a conversation

Choose one of two modes when prompted:

- **A — Paste conversation manually**: Paste any conversation text, then type your question.
- **B — Use a stored lead**: Enter the Lead ID. All stored conversations for that lead are loaded and a preview is shown. Then type your question — the AI answers based on the full history.

---

### 3 — Find leads scheduled on a specific date

Enter a date in the format `24 Sep 2026`. Optionally enter a time filter (e.g. `11:00 AM`). The tool searches all stored leads whose AI-extracted follow-up date matches.

---

### 4 — View conversation history for a lead

Enter a Lead ID to see all past conversations with dates, BDE IDs, AI analysis summaries, and pain points.

---

### 5 — List all leads

Displays a table of all leads with their total conversation count and date of last contact.

---

## Data storage

All data is stored locally in:

```
conversation_ai/data/conversations.db
```

This is a standard SQLite database file. To browse it visually, install the **SQLite Viewer** extension in VS Code or download **DB Browser for SQLite** from [https://sqlitebrowser.org](https://sqlitebrowser.org).

---

## Project structure

```
conversation_ai/
├── cli.py                  ← Run this to start the terminal tool
├── main.py                 ← FastAPI backend (for API access if needed)
├── .env                    ← Your API key (create this yourself)
├── requirements.txt        ← Python dependencies
├── data/
│   └── conversations.db    ← Auto-created; stores all conversations
├── services/
│   ├── llm_client.py       ← Gemini AI client
│   ├── database.py         ← SQLite read/write functions
│   ├── reminder_service.py ← Reminder status computation (no AI)
│   ├── followup_rules.py   ← Follow-up day rules by priority
│   ├── notification_service.py ← Date/client filtering (no AI)
│   └── utils.py            ← Lead ID normalisation
├── schemas/
│   └── conversation_analysis.py ← Pydantic data models
└── prompts/
    ├── analysis_prompt.py  ← AI analysis prompt
    └── qa_prompt.py        ← AI Q&A prompt
```

---

## Notes

- The AI model used is `gemini-2.0-flash-lite` by default — fast and within the free quota.
- Responses from the AI typically take 3–8 seconds depending on conversation length and history size.
- No internet connection is needed except for the Gemini API call itself.
- The `.env` file contains your private API key — do not share it.
