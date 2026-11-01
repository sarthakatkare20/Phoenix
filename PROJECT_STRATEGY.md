# PHOENIX (JARVIS) — ARCHITECTURAL STRATEGY & ROADMAP
> **Purpose**: Single source of truth for architectural decisions, hardware limits, tool evaluations, and development milestones. This document prevents "time-sink" traps and keeps the project grounded in reality.

---

## 1. PHOENIX MASTER VISION (THE NORTH STAR)
Phoenix is envisioned as a **fully autonomous, persistent, 24/7 personal digital companion and operating system agent (Jarvis)**. 

The ultimate system must deliver on these **15 core capabilities**:

### 🌐 A. Foundational & Operational Freedom
1. **24/7 Persistent Availability**: Runs continuously as a reliable system daemon on your Windows machine without crashes, memory leaks, or manual restarts.
2. **Zero Mandatory Paid Subscriptions**: 100% functional on local open-source models with zero mandatory cloud API costs.
3. **Local Open-Source LLM First**: Powered locally by fast, quantized open-source models (Ollama / llama.cpp) running directly on your laptop.
4. **Intelligent Multi-Model Routing**: Automatically routes simple/fast tasks to local LLMs (e.g., Qwen/Hermes), and heavy reasoning/coding tasks to cloud models (e.g., Gemini Pro via Jio) with seamless fallbacks.
5. **Secure Remote Access**: Full control and chat availability from your phone/outside network via encrypted peer-to-peer tunnels (Tailscale) or messaging gateways (Telegram/Discord) with strict authentication.

### 🎙️ B. Interface & Cognitive Perception
6. **Ultra-Natural Voice Conversation**: Sub-second, conversational voice loop with accurate STT (Whisper), natural human-like TTS (Kokoro), and instant **barge-in** (stops talking immediately when you speak).
7. **Holographic Visual Interface**: Iron Man-style 3D reactive HUD and Arc Reactor displaying real-time system state, telemetry, and media.
8. **Persistent Semantic Long-Term Memory**: Remembers who you are, your preferences, past conversations, ongoing projects, and personal facts across years—indexed semantically (not just keyword matching).
9. **Proactive Contextual Intelligence**: Doesn't just wait for prompts; proactively notices important events (calendar alerts, low battery, hardware thermal stress, reminders) and speaks or acts when appropriate.

### ⚡ C. Autonomous Agency & Tools
10. **Dynamic Skills Architecture**: Ability to install, discover, and dynamically register new capabilities (tools, plugins, and workflows) without restarting the core server.
11. **Self-Evolution & Skill Creation**: Ability to generate, test, and save new skills on-the-fly with explicit user confirmation and approval.
12. **Multi-Agent Orchestration**: Ability to spawn and coordinate specialized subagents (e.g., a Researcher agent gathering web data while a Coder agent edits files).
13. **True Autonomous Task Execution**: Multi-step goal execution with real verification loops, self-correction on failure, and rollbacks instead of simulated mocks.
14. **Background Execution When Absent**: Can be assigned a task (e.g., "Monitor this website", "Scrape this data", "Send this report at 8 PM") and executes it independently while you are away from the computer.

### 💼 D. Real-World Utility Domains
15. **Specialized Assistance Modules**:
    - **Personal Secretary**: Instant voice notes, to-do lists, calendar management, and timer/reminders.
    - **Coding & Web Development**: Local codebase inspection, AST search, diff application, test running, and scaffolding projects.
    - **Business & Outreach**: Lead tracking, CRM contact management, email drafting, and structured outreach automation.
    - **Deep OS & Media Automation**: Spotify playback, volume/window control, app management, and file system navigation.

> **Architectural Law**: *The Master Vision defines WHERE we are going. The Incremental Roadmap defines HOW we build the foundation to get there without collapsing.*

---

## 2. THE AGENCY MULTI-AGENT ARCHITECTURE (PHOENIX & HIS SPECIALIST TEAM)
Instead of a single overloaded chatbot, Phoenix operates as an **AI Agency Operating System** with a hierarchical team:

```
                                  👑 USER (SARTHAK)
                                         │  (Voice / Web UI / Telegram)
                                         ▼
                             ⚡ PHOENIX (The CEO / Boss)
                   Orchestrator • Fast Voice • Task Delegation
                                         │
       ┌──────────────────┬──────────────┴──────────────┬──────────────────┐
       ▼                  ▼                             ▼                  ▼
  👨‍💻 MARK           🦈 THE SHARKS                  🎯 THE HUNTER        📋 SECRETARY
(Lead Tech / Code) (Business & Strategy Debate)  (Lead Gen / Clients) (Notes, Todos, Reminders)
• Writes/tests code • Stress-tests agency ideas  • Scrapes leads      • Daily planner
• Uses Gemini Pro   • "Shark Tank" roast/audit   • Drafts outreach    • SQLite DB
• Project specs     • Pricing & pitch decks      • Client research    • Local fast tasks
```

### Team Profiles & Responsibilities:

#### 1. ⚡ Phoenix (The Boss / Orchestrator)
- **Role**: Chief Executive Assistant & Direct Interface to Sarthak.
- **Engine**: Fast local model (`qwen2.5:3b` / `llama3.2:3b`) + Voice Loop (Whisper + Kokoro).
- **Function**: Greets user, maintains overall context, delegates complex questions to specialized subagents, and synthesizes answers into a single crisp voice response.

#### 2. 👨‍💻 Mark (Lead Software Engineer & Code Architect)
- **Role**: Technical co-founder & Senior Developer.
- **Engine**: Powered by **Gemini 2.5 Pro** (via free Jio API) for deep 1M+ token context and elite coding reasoning.
- **Function**: Writes and refactors code, designs database schemas, reads repositories, debugs errors, and drafts technical specifications.

#### 3. 🦈 The Sharks (The Devil's Advocate / Business Strategy Panel)
- **Role**: Ruthless business auditors & agency advisors.
- **Engine**: High-reasoning model (Gemini Pro / Claude reasoning prompt).
- **Function**: When Sarthak discusses a new client proposal, service package, or pricing idea, the Sharks argue the other side:
  - *"Is the pricing sustainable?"*
  - *"Where is scope creep going to kill our profit margin?"*
  - *"Why would a client reject this pitch deck, and how do we counter it?"*

#### 4. 🎯 The Hunter (Client Acquisition & Lead Generation)
- **Role**: Agency business development representative.
- **Engine**: Web Search tools + Browser scraping + Cold outreach copywriter.
- **Function**: Finds targeted businesses (e.g. local clinics, real estate, e-commerce brands), gathers contact info, analyzes their current website/social weaknesses, and drafts hyper-personalized cold pitch emails.

#### 5. 📋 The Secretary (Operations & Daily Workflow)
- **Role**: High-speed executive administrator.
- **Engine**: Fast local LLM + SQLite (`phoenix.db`) + `APScheduler`.
- **Function**: Manages to-do lists, quick voice notes, follow-up alarms, and daily morning agency briefings.

---

## 3. HARDWARE BASELINE & STRICT BUDGET
All engineering decisions must respect this physical ceiling:

| Component | Specification | Operational Constraint |
| :--- | :--- | :--- |
| **CPU** | Intel Core i5 13th Gen | Host for Kokoro TTS, SQLite, Embeddings, and Background Tasks. |
| **GPU / VRAM** | NVIDIA RTX 3050 (6GB VRAM) | **Hard limit**: 6.0 GB total VRAM. |
| **System RAM** | 16 GB | OS + Chrome WebGL + Python processes. |
| **Operating System** | Windows 11 | Direct process control, media keys, audio drivers. |

### Strict VRAM Allocation Budget:
* **Windows DWM + Chrome 3D UI**: ~1.5 GB
* **Speech-to-Text (`faster-whisper` INT8)**: ~0.5 GB (or CPU offload)
* **Text-to-Speech (`kokoro-onnx`)**: 0.0 GB (runs purely on CPU)
* **Maximum Available VRAM for LLM**: **~2.5 GB to 3.0 GB**
* **Local Model Fit**: `qwen2.5:3b-instruct` / `llama3.2:3b` / `hermes3:8b` (quantized Q3/Q4 with layer offloading).
* **Heavy Tasks / Coding**: Route to **Gemini 2.5 Pro (Free Jio Subscription)** instead of crashing local VRAM.

---

## 4. THE CORE PHILOSOPHY: "LEVERAGE, DON'T REINVENT"
The #1 reason AI projects become time-sinks is writing custom plumbing for solved problems.
* **Never write custom regex** to parse user intent when native LLM Tool Calling (JSON Schema) exists.
* **Never build a custom multi-step planner** with hardcoded string matches when agentic frameworks exist.
* **Never maintain two separate backends** (Node.js + Python). Python is the native home for AI, Voice, and ML.
* **Never write custom audio queue locking** when proven voice pipelines exist.

---

## 5. OPEN-SOURCE TOOL ARSENAL EVALUATION

### A. The Brain & Agent Framework: `NousResearch/hermes-agent`
* **What it is**: An autonomous, self-improving agent framework by Nous Research.
* **Key Capabilities to Leverage**:
  - **Self-Evolution & Skills**: Creates and refines skills from real interactions.
  - **Built-in Tools**: File read/write/patch, terminal execution, browser CDP automation.
  - **Task & Time Management**: Native `todo` tool and `cronjob` (background task scheduling).
  - **Official Plugins**: Direct integrations (Spotify, Home Assistant, etc.).
  - **Gateways**: Chat remotely via Telegram / Discord without writing custom tunnel auth.
* **Decision**: Study and evaluate as the primary candidate for the core Brain engine.

### B. Fallback / Alternative Brain Stack: `LiteLLM` + `PydanticAI`
* **LiteLLM**: Unified 1-line interface to switch seamlessly between local Ollama and cloud Gemini.
* **PydanticAI**: Type-safe Python tool-calling framework (turns simple Python functions into LLM tools).

### C. Voice Pipeline (Ear & Mouth):
* **Silero VAD**: Low-latency local voice activity detection (keep from existing code).
* **`faster-whisper` (`base.en` / `small.en`)**: Local, offline STT (keep from existing code).
* **`kokoro-onnx`**: Ultra-lightweight 82M natural TTS running on CPU (keep from existing code).

### D. Storage & Memory:
* **SQLite (`phoenix.db`)**: Single-file, zero maintenance, ACID-compliant database.
* **Schema**:
  - `notes` (id, title, content, tags, created_at)
  - `todos` (id, task, priority, status, due_date)
  - `reminders` (id, message, fire_at, status)
  - `user_profile` (key, value, updated_at)

### E. The Face (UI):
* **React 19 + Three.js Hologram (`src/`)**: Keep existing visualizer, but **freeze development**. No more time spent on shaders or animations until core utility is proven.

---

## 6. PROJECT SCOPE LOCK (THE PERSONAL DESKTOP SECRETARY)

### ✅ IN SCOPE (What Phoenix DOES in Phase 1 MVP):
1. **Natural Voice Interaction**: Instant speech input, crisp answers, interruption / barge-in support.
2. **Personal Secretary Utilities**:
   - **Notes**: Take quick spoken notes and retrieve them.
   - **To-Do Lists**: Add tasks, check off completed items, list pending tasks.
   - **Reminders & Timers**: Schedule background alerts ("Remind me in 20 minutes to call mom").
3. **Local Desktop Controls**: Volume, media playback (Spotify), system stats (battery, CPU).
4. **Intelligent Suggestions**: Fast conversational answers with web search capability.

### ❌ OUT OF SCOPE FOR MVP (Phased to Milestone 4+):
- Full autonomous CRM outreach campaigns.
- Multi-agent autonomous swarms running in background.
- Direct vector database infrastructure.

---

## 7. INCREMENTAL IMPLEMENTATION ROADMAP

```
┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐
│    MILESTONE 1     │ ──► │    MILESTONE 2     │ ──► │    MILESTONE 3     │
│ Backend Declutter  │     │ Core Voice-to-Tool │     │ Secretary Utilities│
│ & Unification      │     │ Pipeline (< 1.5s)  │     │ (Notes, Todos, DB) │
└────────────────────┘     └────────────────────┘     └────────────────────┘
                                                                │
                                                                ▼
                                                       ┌────────────────────┐
                                                       │    MILESTONE 4     │
                                                       │ The Agency Team    │
                                                       │ Mark, Sharks, Hunt │
                                                       └────────────────────┘
```

### Milestone 1: Declutter & Unification
- [ ] Freeze `bridge/server.mjs` (Node.js) and select Python as the single backend host.
- [ ] Create clean, locked `requirements.txt` for Python dependencies.
- [ ] Connect React frontend WebSocket directly to Python server (`ws://localhost:8000`).

### Milestone 2: The Core Loop (Ear -> Brain -> Mouth)
- [ ] Wire Silero VAD + Whisper + Ollama + Kokoro into one reliable, crash-free pipeline.
- [ ] Ensure sub-1.5s first-token spoken response latency.
- [ ] Test interruption / barge-in reliability.

### Milestone 3: Real Utility Tools & Storage
- [ ] Initialize `phoenix.db` (SQLite) with `notes`, `todos`, and `reminders` tables.
- [ ] Implement typed tool functions: `add_note`, `get_notes`, `add_todo`, `list_todos`, `set_reminder`.
- [ ] Add `APScheduler` for background reminder dispatch.

### Milestone 4: The Agency Multi-Agent System
- [ ] Setup **Mark** (Coding Agent powered by Gemini 2.5 Pro with filesystem tools).
- [ ] Setup **The Sharks** (Business Devil's Advocate prompt & debate framework).
- [ ] Setup **The Hunter** (Lead scraping & personalized outreach templates).
- [ ] Evaluate `NousResearch/hermes-agent` as the underlying agent harness.

---

## 8. DECISION LOG & OPEN DISCUSSION
*Record key architectural discussions and conclusions here:*

* **2026-11-01**: Decided to stop building custom plumbing from scratch. Evaluated `NousResearch/hermes-agent` for autonomous tooling, memory, and plugins. Agreed to focus on a lightweight Personal Secretary MVP (Notes, To-Dos, Reminders, Voice) backed by SQLite before touching advanced multi-agent or CRM features.
