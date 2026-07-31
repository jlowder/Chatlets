# Chatlets — Agno Backend

## Overview

A **backend-only** implementation using [Agno](https://github.com/agno-agi/agno) for the Chatlets project. It consists of two services:

1. **Flask agent service** (`agent_service.py`) — Python service on port **8081** that runs an Agno agent with bash tool execution
2. **Next.js proxy** — lightweight proxy on port **3001** that exposes `/api/chat` for the shared frontend to consume

The shared frontend proxies to this backend and renders all UI.

---

## Running

```bash
cd agno
pip install -r requirements.txt    # Python deps (first time)
npm install                         # Node deps (first time)
npm run dev:all                     # starts Flask agent + Next.js proxy together
```

This backend has **two internal services** that must both run:

| Service | Command | Port | What it does |
|---------|---------|------|-------------|
| Flask Agent | `npm run agent` | 8081 | Runs the Agno AI agent with bash tool execution |
| Next.js Proxy | `npm run dev` | 3001 | Proxies `/api/chat` to the Flask agent |

Running `npm run dev` alone will **not** work — you must use `npm run dev:all` to start both services.

The shared frontend proxies `/api/chat` to port 3001 (`CHATLET_BACKEND=agno`).

---

## Architecture

```
┌──────────────────────┐         ┌──────────────────────────┐         ┌──────────────────────────┐
│   Shared Frontend    │  proxy  │  agno Next.js Proxy      │  proxy  │  agno Flask Agent        │
│  (Next.js, :3000)    │──────▶  │  (Next.js, :3001)        │──────▶  │  (Flask, :8081)          │
│                      │         │                          │         │                          │
│  CHATLET_BACKEND     │         │  /api/chat ──────▶ /chat │         │  /chat  — agent.run()    │
│  =agno               │         │                          │         │  /health — health check  │
└──────────────────────┘         └──────────────────────────┘         │                          │
                                                                     │  ┌────────────────────┐  │
                                                                     │  │ Agent.run()        │  │
                                                                     │  │  - Agno agent      │  │
                                                                     │  │  - tool_call_limit │  │
                                                                     │  │  - bash tool       │  │
                                                                     │  └─────────┬──────────┘  │
                                                                     │            │              │
                                                                     │            ▼              │
                                                                     │  ┌──────────────────┐    │
                                                                     │  │ OpenAI-Compat    │    │
                                                                     │  │ (config.json)    │    │
                                                                     │  └──────────────────┘    │
                                                                     └──────────────────────────┘
```

---

## API Contract

### Flask Service (`POST /chat` on :8081)

**Request body:**
```json
{
  "messages": [
    { "role": "user", "content": "What is the area of Arizona?" },
    { "role": "assistant", "content": "Arizona has an area of approximately 113,998 square miles." },
    { "role": "user", "content": "And the population?" }
  ]
}
```

**Response:**
```json
{
  "text": "string",
  "toolOutputs": [{ "stdout": "...", "stderr": "...", "error": "..." }]
}
```

### Proxy (`POST /api/chat` on :3001)

Forwards the request body to Flask's `/chat` and returns the response unchanged.

---

## Service Details

### Flask Agent Service (`agent_service.py`)

**Port:** 8081

Python Flask server that hosts an Agno agent with bash tool execution.

**Key components:**
- `Agent` with `OpenAILike` model provider, `bash_tool`, and `tool_call_limit=5`
- `bash_tool()` — executes commands via `subprocess.run()` with 30s timeout
- `/health` endpoint for readiness checks
- `/chat` endpoint — the main API

**Bash tool:**
- Uses `subprocess.run(command, shell=True, timeout=30)`
- Checks allow list from `config.json` before execution
- Returns JSON string: `{"stdout": "...", "stderr": "..."}` on success
- Returns `{"error": "...", "stdout": "", "stderr": ""}` on failure

**Allow list:** (from `config.json`)
| Mode | Behavior |
|------|----------|
| `allowAll: true` | All commands execute |
| `allowAll: false` | Only commands whose base (first word) is in `allowList` |

Default allow list: `["ls", "pwd"]`

### Next.js Proxy (`app/api/chat/route.ts`)

**Port:** 3001

Minimal proxy — forwards `POST /api/chat` to `http://localhost:8081/chat` unchanged. Handles 502 errors when Flask is unavailable.

---

## Session Memory

The API supports full conversation history. Every request sends the complete message array, allowing the agent to reference prior turns. The last message in the array is always the new user input; all prior messages provide context.

- **Request shape**: `{ messages: Array<{ role: "user" | "assistant", content: string }> }`
- **History length**: No hard limit — the full conversation is sent each turn
- **Fallback**: If the request contains only `{ prompt: string }` (legacy format), the backend treats it as a single-user-message conversation

### Implementation (agno)

The backend builds a full conversation string from the messages array and passes it as input to `agent.run()`:

```python
# Backend receives { messages: [{role, content}, ...] }
conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
result = agent.run(input=conversation)
```

## LLM Configuration

Shared `config.json` read by both Flask and Next.js proxy:

```json
{
  "provider": "YOUR_PROVIDER",
  "baseURL": "http://localhost:8080/v1",
  "apiKey": "your-api-key",
  "model": "model-name",
  "allowList": ["ls", "pwd"],
  "allowAll": false
}
```

---

## Code Structure

```
agno/
├── agent_service.py           # Flask agent service (port 8081)
├── app/api/chat/route.ts      # Next.js proxy (port 3001)
├── config.json                # LLM config + allow list
├── requirements.txt           # Python dependencies
├── scripts/find-python.mjs    # Auto-detect Python from venv
├── package.json
├── tsconfig.json
└── SPEC.md
```

### `scripts/find-python.mjs`

Auto-detects Python from local virtual environments (`.venv`, `venv`, `.env`, `env`) and runs `agent_service.py`. Used by `npm run agent:venv`.

---

## Integration with Shared Frontend

The shared frontend (`shared/`) serves as the single UI for all Chatlets backends. When `CHATLET_BACKEND=agno`, it proxies `/api/chat` to `http://localhost:3001/api/chat` (Next.js proxy), which then forwards to Flask's `/chat` on port 8081.

| Env var | Proxy chain |
|---------|-------------|
| `CHATLET_BACKEND=vercel-ai` | Frontend :3000 → `localhost:4000/api/chat` |
| `CHATLET_BACKEND=agno` | Frontend :3000 → `localhost:3001/api/chat` → `localhost:8081/chat` |

---

## Python Dependencies

```
agno
flask
flask-cors
openai
```

Install with: `pip install -r requirements.txt`
