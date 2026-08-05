# Database expectations and design

This document describes the database expectations and design of the Agno backend, explaining why a persistent database is not part of this architecture and how stateless message histories are handled instead.

## Design Philosophy

The Agno edition of Chatlets is designed as a **stateless split-backend service**. It does not maintain any persistent databases (such as SQLite, PostgreSQL, or Redis) for state or message logging on the backend server.

### Why No Database?
1. **Stateless Operations:** The React frontend (under `shared/`) acts as the single source of truth for the conversation history. It stores the accumulated turns (user inputs, assistant replies, and nested tool execution results) inside its own component state.
2. **Stateless Payload Transmission:** On every new request to `/api/chat` -> `/chat`, the entire conversation history is transmitted from the frontend in the HTTP POST request payload.
3. **In-Memory History Processing:** The Python Flask service (`agent_service.py`) dynamically maps this payload history into standard structured `agno.models.message.Message` objects in-memory for the current agent run turn.
4. **Boundary Isolation:** The backend isolates the current turn's tool execution outputs by locating the last user query using a backward search, cleanly preventing older tool results from leaking.

## Silencing Agno Database Warnings

By default, the Agno SDK provides several agent options that log database-related warnings when enabled without an assigned SQLite/component database (e.g. `add_history_to_context=True` or `add_session_state_to_context=True`).

To align with the stateless architecture and silence these database warnings, the agent in `agno/agent_service.py` is configured with:
```python
agent = Agent(
    name="chat-agent",
    model=model,
    tools=[bash_tool],
    # ...
    add_session_state_to_context=False,
    add_history_to_context=False,
)
```
By explicitly setting both options to `False`, we indicate to the Agno SDK that history is managed manually/statelessly, successfully silencing any database-backed log warnings.

## Future Considerations
If a persistent database is eventually desired (e.g. for server-side multi-session storage), Agno natively supports storage components (such as `SqlAgentStorage`) that can be passed to the `Agent(storage=...)` parameter. However, this is not part of the core stateless sandboxed design of this project.
