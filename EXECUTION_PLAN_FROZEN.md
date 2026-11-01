# PHOENIX — FROZEN EXECUTION PLAN (SCOPE LOCKED 🔒)
> **THE IRON RULE**: 
> **Zero new features can be added until every checkbox in this document is marked [x].**
> Any new idea that pops into our heads (3D gestures, new plugins, new UI tricks) goes directly into the **"PARKED FOR V2"** section at the bottom. No exceptions.

---

## 🎯 THE 4-PHASE LOCKED ROADMAP

```
┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐
│      PHASE 1       │ ──► │      PHASE 2       │ ──► │      PHASE 3       │ ──► │      PHASE 4       │
│ Clean & Unify      │     │ The Voice Loop     │     │ Secretary & DB     │     │ The Agency Team    │
│ (Single Backend)   │     │ (Sub-1.5s Voice)   │     │ (Notes, Todos, DB) │     │ (Mark, Sharks, Hunt│
└────────────────────┘     └────────────────────┘     └────────────────────┘     └────────────────────┘
```

---

## 🧹 PHASE 1: THE CLEANUP & UNIFICATION (Days 1–2)
*Goal: Kill the dual-backend confusion. Run 1 frontend + 1 clean Python backend.*

- [x] **Step 1.1: Dependency Lock**
  - Create a clean `requirements.txt` with exact working versions:
    (`fastapi`, `uvicorn[standard]`, `faster-whisper`, `kokoro-onnx`, `onnxruntime`, `sounddevice`, `numpy`, `httpx`, `apscheduler`, `duckduckgo-search`).
- [ ] **Step 1.2: Remove Dead Code & Mocks**
  - Remove/Archive `bridge/` (the duplicate Node.js server).
  - Remove fake regex planner files from `paaro/reasoning/` (replace with native tool definitions).
  - Remove fake telemetry fallback in `src/lib/proactive.ts`.
- [x] **Step 1.3: Unify Network Port**
  - Point frontend `src/config.ts` to `ws://localhost:8000` (FastAPI).
  - Update `scripts/start.mjs` (or create a simple `start.bat`) that runs:
    1. Python FastAPI (`paaro.server:app` on port 8000)
    2. Vite frontend (`npm run dev` on port 5173)
- [ ] **Phase 1 Verification**:
  - Run the start script. Browser opens, 3D Arc Reactor loads, WebSocket connects to FastAPI with 0 errors.

---

## 🎙️ PHASE 2: THE ROCK-SOLID VOICE LOOP (Days 3–5)
*Goal: Speak to Phoenix -> Fast response back in under 1.5 seconds. 100% crash-free.*

- [ ] **Step 2.1: Streaming Audio Pipeline**
  - Browser mic streams raw audio chunks -> FastAPI WebSocket.
  - Silero VAD detects speech start and end accurately without clipping.
- [ ] **Step 2.2: Fast Local Transcription (STT)**
  - `faster-whisper` (`base.en`, INT8) transcribes audio into clean text.
- [ ] **Step 2.3: Fast Local Brain (LLM)**
  - Route transcribed text to local Ollama (`qwen2.5:3b-instruct` or `llama3.2:3b`).
  - Stream response tokens back in real-time.
- [ ] **Step 2.4: Natural Neural Voice (TTS)**
  - `kokoro-onnx` converts response tokens into speech chunks on CPU.
  - Stream audio directly back to browser speakers.
- [ ] **Step 2.5: Verified Barge-in**
  - User starts speaking while Phoenix is talking -> Phoenix immediately silences and listens.
- [ ] **Phase 2 Verification**:
  - Say *"Hey Jarvis, who are you?"* -> Natural Kokoro voice speaks back in under 1.5s. Speak midway -> Phoenix stops instantly.

---

## 📋 PHASE 3: THE SECRETARY & DATABASE (Days 6–8)
*Goal: Phoenix becomes genuinely useful for daily tasks (Notes, Todos, Reminders).*

- [ ] **Step 3.1: SQLite Database Setup (`phoenix.db`)**
  - Create clean tables:
    - `notes` (id, title, content, created_at)
    - `todos` (id, task, status, priority, created_at)
    - `reminders` (id, message, fire_at, status)
- [ ] **Step 3.2: Typed Tool Functions (Zero Regex)**
  - `add_note(title, content)`
  - `get_notes()`
  - `add_todo(task, priority)`
  - `list_todos(status)`
  - `complete_todo(task_id)`
  - `set_reminder(message, delay_minutes)`
- [ ] **Step 3.3: Background Scheduler**
  - Connect `APScheduler` so when a reminder time hits, Phoenix notifies you or speaks.
- [ ] **Phase 3 Verification**:
  - Spoken command: *"Take a note that tomorrow I have a meeting at 4 PM."* -> Stored in SQLite.
  - Spoken command: *"What are my pending tasks?"* -> Lists actual database records.

---

## 🚀 PHASE 4: THE AGENCY SPECIALIST TEAM (Days 9–14)
*Goal: Activate Mark (Coder), The Sharks (Business Strategy), and The Hunter (Lead Gen).*

- [ ] **Step 4.1: Mark (Lead Developer)**
  - Connect Gemini 2.5 Pro (via Jio free API key).
  - Give Mark real filesystem tools (`read_file`, `write_file`, `list_directory`).
  - Command: *"Mark, inspect this folder and write a clean script to do X."*
- [ ] **Step 4.2: The Sharks (Business & Strategy Auditor)**
  - Setup high-reasoning debate prompt for proposal and pricing critique.
  - Command: *"Sharks, audit this agency pitch deck: ₹1.5L for custom e-commerce site."* -> Brutally analyzes margins, scope, and risks.
- [ ] **Step 4.3: The Hunter (Lead Generation & Research)**
  - Connect `duckduckgo-search` and `Crawl4AI` (100% free open-source).
  - Command: *"Find 5 dental clinics in Pune without modern mobile websites."* -> Returns structured lead list.
- [ ] **Phase 4 Verification**:
  - Mark writes a working script. Sharks critique a business proposal. Hunter extracts real web leads.

---

## 🛑 PARKED FOR V2 (DO NOT TOUCH RIGHT NOW)
*These ideas are forbidden until Phase 1–4 are 100% complete:*
1. 3D Hand gesture tracking & camera pinch controls.
2. Self-evolving prompt optimization frameworks.
3. Complex multi-node Docker deployments.
4. Social media automated posting bots.
5. In-depth vector databases (Pinecone/Chroma).
