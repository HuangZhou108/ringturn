# RingTurn

[![en](https://img.shields.io/badge/lang-English-red.svg)](./README.en.md)
[![zh](https://img.shields.io/badge/lang-中文-blue.svg)](./README.md)

RingTurn is an AI-assisted music adaptation application for creating personalized ringtones.
Users upload MP3/WAV audio, describe the desired result in natural language, and optionally
set instrument, tempo, and duration. A LangGraph workflow performs analysis, melody
extraction, MIDI generation, arrangement, rendering, and quality checks.

> Implementation baseline: October 2026. Historical requirement and UI design documents
> are retained for design traceability and may not describe the current code.

## Disclaimer

This is an undergraduate course project at Nanjing University and is provided for
educational use only. Users are responsible for having the rights to uploaded audio.
Generated content is intended for personal, non-commercial use. The software is provided
“as is”, and third-party dependencies are subject to their own licenses.

## Current capabilities

- A complete audio-to-ringtone pipeline: source acquisition, analysis, melody extraction,
  MIDI generation, arrangement, rendering, quality checks, and reflection.
- A hybrid Agent architecture: deterministic main graph and domain subgraphs, with optional
  function calling during arrangement and a deterministic fallback.
- Melody-source selection, multiple extraction candidates, stabilization, key/octave
  correction, quality scoring, and bounded revision loops.
- Durable task leases, heartbeats, duplicate-execution protection, startup recovery, and
  LangGraph SQLite checkpoints.
- Persistent task events, multi-client WebSocket delivery, cursor-based replay, structured
  traces, and sanitized error diagnostics.
- Post-result feedback tasks and in-flight human intervention with pause, answer, and resume.
- Persistent RAG knowledge documents and Profile-scoped long-term memory with relevance
  retrieval, deduplication, decay, importance, and retention limits.
- Local Profiles, preferences, configurable tool graphs, conversation history, and Chinese/
  English UI resources.

## Architecture

```text
React UI
  → FastAPI REST / WebSocket
  → durable task scheduler
  → AgentExecutor
  → LangGraph main workflow
  → analysis / melody / arrangement / quality subgraphs
  → atomic audio and MIDI tools
  → task database + checkpoint database
  → persistent event stream → UI
```

Main workflow:

```text
entry_router
  → fetch_source
  → analyze_structure
  → extract_melody
  → generate_midi
  → arrange
  → render
  → check_quality
  → reflect
  → retry_router → END / arrange
```

## Quick start

### Requirements

- Node.js 18.18 or newer
- Python 3.10 recommended; Python 3.11 is also supported by the current audio stack
- FFmpeg for probing, clipping, and conversion
- FluidSynth 2.3 or newer
- A General MIDI SoundFont (`.sf2`)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173/`.

### Backend

```bash
conda create -n ringturn python=3.10
conda activate ringturn
cd backend
pip install -r requirements.txt
```

Create `backend/.env`:

```env
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4
LLM_BASE_URL=

DATABASE_URL=sqlite:///./ringturn.db
CHECKPOINT_DB_URL=sqlite:///./checkpoints.db
FLUIDSYNTH_PATH=fluidsynth
SOUNDFONT_PATH=./soundfonts/default.sf2

AGENT_PIPELINE_TIMEOUT_SECONDS=1800
AGENT_TOOL_TIMEOUT_SECONDS=180
AGENT_LEASE_SECONDS=120
AGENT_HEARTBEAT_SECONDS=30
AGENT_RECOVER_ON_STARTUP=true

RAG_TOP_K=4
MEMORY_TOP_K=6
MEMORY_MAX_PER_PROFILE=200
MEMORY_HALF_LIFE_DAYS=90
```

Start the API:

```bash
python -m app.main
# or
uvicorn app.main:app --reload
```

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Task states and events

```text
pending → planning → executing → completed
                        ├──────→ failed
                        ├──────→ cancelled
                        └──────→ waiting_input → pending
```

`completed`, `failed`, and `cancelled` are terminal. Cancellation is idempotent, and late
execution results cannot overwrite a persisted terminal state.

WebSocket endpoint:

```text
ws://localhost:8000/ws/chat/{task_id}?after_event_id={cursor}
```

Clients retain the latest `event_id` and provide it on reconnection to replay missed events.

## Selected API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/upload` | Upload audio |
| POST | `/api/v1/tasks` | Create a task |
| GET | `/api/v1/tasks/{task_id}/status` | Read task and intervention state |
| GET | `/api/v1/tasks/{task_id}/trace` | Read sanitized diagnostics |
| GET | `/api/v1/tasks/{task_id}/result` | Read the generated result |
| DELETE | `/api/v1/tasks/{task_id}` | Idempotently cancel a task |
| POST | `/api/v1/tasks/{task_id}/feedback` | Create a feedback revision |
| POST | `/api/v1/tasks/{task_id}/interventions` | Pause for human input |
| POST | `/api/v1/tasks/{task_id}/interventions/{id}/response` | Answer and resume |
| GET/POST | `/api/v1/profiles/{profile_id}/memories` | Manage long-term memory |
| GET | `/api/v1/knowledge/search` | Search arrangement knowledge |

The complete API documentation is maintained in Chinese in
[docs/接口文档.md](./docs/接口文档.md).

## Tests

```bash
cd backend
python -m pytest -q
python -m compileall -q app tests
python -m ruff check app tests --select=F821,F822,F823 --ignore=I
```

Current regression baseline: `114 passed, 3 skipped`.

## Documentation

- [Documentation index](./docs/README.md) (Chinese)
- [Agent design](./docs/Agent详细设计.md) (Chinese)
- [Observability and resilience](./docs/Agent执行可观测性.md) (Chinese)
- [Runtime continuity and HITL](./docs/Agent运行时连续性.md) (Chinese)
- [RAG and long-term memory](./docs/RAG与长期记忆.md) (Chinese)

## Current boundaries

- Scheduling uses database leases and process-local async runners rather than a dedicated
  distributed queue.
- RAG uses persistent local documents and lightweight hybrid retrieval, not an external
  vector database or embedding service.
- Output quality depends on source material, models, SoundFont, and local binaries. RingTurn
  is a course and engineering project, not a professional mastering system.
