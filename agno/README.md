# Chatlet — Agno Edition

A minimal chat interface powered by [Agno](https://docs.agno.com/) — the Python agent framework.

## Architecture

This project combines:
- **Next.js (TypeScript)** — Frontend chat UI + API proxy route
- **Agno (Python)** — Agent service with bash tool execution via Flask

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐
│ Browser  │────▶│ Next.js      │────▶│ Flask Agent   │
│ (UI)     │     │ API /chat    │     │ Service       │
│          │◀────│ (proxy)      │◀────│ (Python)      │
└──────────┘     └──────────────┘     └───────┬───────┘
                                               │
                                               ▼
                                        ┌───────────────┐
                                        │ OpenAI-Compat │
                                        │ LLM Server    │
                                        └───────────────┘
```

## Quick Start

### 1. Install Python dependencies

```bash
cd /Users/jlowder/dev/chatlets/agno
pip install -r requirements.txt
```

### 2. Install Node.js dependencies

```bash
cd /Users/jlowder/dev/chatlets/agno
npm install
```

### 3. Configure your LLM

Edit `config.json` to match your OpenAI-compatible LLM:

```json
{
  "provider": "YOUR_PROVIDER",
  "baseURL": "http://localhost:8080/v1",
  "apiKey": "your-api-key",
  "model": "your-model-name",
  "allowList": ["ls", "pwd"],
  "allowAll": false
}
```

### 4. Start the services

**Option A — Run both concurrently (auto-detects venv):**
```bash
npm run dev:all
# or with bun:
bun run dev:all
```

**Option B — Run separately:**
```bash
# Terminal 1 — Python agent service (auto-detects venv)
npm run agent:venv
# or if your venv is not auto-detected, run with explicit path:
/path/to/venv/bin/python agent_service.py

# Terminal 2 — Next.js frontend
npm run dev
```

**Note:** The agent service uses Python 3 with `agno`, `flask`, and `flask-cors`. Install with:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
The `agent:venv` script automatically finds `.venv`, `venv`, `.env`, or `env` directories. You can also set `AGNO_VENV` env var to override.

### 5. Open the app

Visit `http://localhost:3000` in your browser.

## Project Structure

```
agno/
├── app/
│   ├── api/
│   │   └── chat/
│   │       └── route.ts        # Next.js API proxy → Python agent
│   ├── globals.css              # Tailwind CSS 4 import
│   ├── layout.tsx               # Root layout
│   └── page.tsx                 # Chat UI (client component)
├── agent_service.py             # Python Flask + Agno agent service
├── config.json                  # LLM & tool configuration
├── package.json                 # Node.js dependencies
├── postcss.config.mjs           # Tailwind CSS config
├── tsconfig.json                # TypeScript config
├── requirements.txt             # Python dependencies
├── next.config.mjs              # Next.js config
├── next-env.d.ts                # Next.js TypeScript refs
├── SPEC.md                      # Design specification
└── README.md                    # This file
```

## How It Works

1. **User types** a message and clicks Send
2. **Frontend** sends `POST /api/chat` with `{ prompt }`
3. **Next.js API route** proxies to the Python agent service
4. **Flask service** runs an Agno `Agent` with:
   - A configured LLM (OpenAI-compatible)
   - A `bash` tool for shell command execution
   - An allow list for security
5. **Agent** processes the prompt, invokes bash tool if needed
6. **Results** flow back: `{ text, toolOutputs[] }`
7. **Frontend** displays the response with tool output cards

## Bash Tool

The bash tool executes shell commands with:
- **30-second timeout**
- **Allow list** (default: `ls`, `pwd`)
- **JSON return** with `stdout`, `stderr`, and optional `error`

Modify the allow list in `config.json` or enable `allowAll: true` to permit any command.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, Tailwind CSS 4 |
| Backend | Python Flask + Agno 2.x |
| LLM | Any OpenAI-compatible model |
| Config | JSON (config.json) |

## Next Steps (Future Considerations)

- Session persistence via `agent.run(session_id=...)`
- Database-backed memory (SQLite/Postgres)
- Streaming responses with SSE
- Multi-agent teams via Agno `Team`
- Human-in-the-loop tool approvals
- OpenTelemetry observability
