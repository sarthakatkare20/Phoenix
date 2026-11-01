# PHOENIX — 7-DAY BATTLE PLAN (THE MVP SPRINT) ⚡
> **Target**: In 7 days, transform Phoenix from a disconnected collection of files into a fully working, fast, local voice assistant + agency co-pilot with zero paid subscription dependencies.
> **Daily Commitment**: ~1.5 to 2 hours per day.

---

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│    DAY 1    │──►│    DAY 2    │──►│    DAY 3    │──►│    DAY 4    │
│ Cleanup &   │   │ Voice Stack │   │ Fast Brain  │   │ Database &  │
│ Single Port │   │ Ear + Mouth │   │ Groq + VAD  │   │ Secretary   │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
                                                             │
                  ┌─────────────┐   ┌─────────────┐   ┌──────┴──────┐
                  │    DAY 7    │◄──│    DAY 6    │◄──│    DAY 5    │
                  │ Telegram &  │   │ Sharks &    │   │ Mark Coder  │
                  │ Final Test  │   │ Lead Hunter │   │ Gemini Pro  │
                  └─────────────┘   └─────────────┘   └─────────────┘
```

---

### 📅 DAY 1: The Foundation (Cleanup & Single Backend)
* **Goal**: Retire the duplicate Node.js bridge. Run 1 single Python FastAPI server connected to your 3D UI.
* **Tasks**:
  1. Create locked `requirements.txt` with exact working dependencies.
  2. Point frontend WebSocket (`src/config.ts`) to `ws://localhost:8000`.
  3. Create single `run.bat` that boots FastAPI + Vite frontend together.
* **Definition of Done**: 
  - Double-click `run.bat` -> Browser opens -> 3D Arc Reactor loads -> WebSocket status shows **CONNECTED** on port 8000 with 0 errors.

---

### 📅 DAY 2: The Ear & Mouth (Local Voice Stack)
* **Goal**: Make Phoenix hear and speak cleanly without crashing.
* **Tasks**:
  1. Wire browser microphone stream to `silero_vad` (detect speech start & end).
  2. Connect `faster-whisper` (`base.en` / `tiny.en`) for fast speech-to-text.
  3. Connect `kokoro-onnx` TTS on CPU for natural voice playback.
* **Definition of Done**:
  - Say *"Testing audio one two three"* -> Screen shows exact text in under 0.8s -> Kokoro speaks it back smoothly.

---

### 📅 DAY 3: The Sub-Second Brain (Groq + Barge-In)
* **Goal**: The "Real Jarvis" speed. Instant responses with verified interruption.
* **Tasks**:
  1. Connect free Groq API key (`llama-3.1-8b-instant`).
  2. Stream tokens from Groq directly into Kokoro TTS chunker.
  3. Test **Barge-in**: Speak while Phoenix is talking -> Phoenix immediately stops speaking and listens.
* **Definition of Done**:
  - Ask *"Who are you and what can you do?"* -> Phoenix starts speaking in under **0.4 seconds**! Speak midway -> Phoenix cuts off instantly.

---

### 📅 DAY 4: The Secretary (SQLite Notes, Todos & Reminders)
* **Goal**: Give Phoenix real, persistent memory on your laptop hard drive.
* **Tasks**:
  1. Initialize SQLite database `phoenix.db` (`notes`, `todos`, `reminders`).
  2. Create native typed tools:
     - `add_note(title, content)`
     - `get_notes()`
     - `add_todo(task, priority)`
     - `list_todos(status)`
* **Definition of Done**:
  - Say *"Phoenix, note down that client meeting is tomorrow at 4 PM."* -> Saved in SQLite.
  - Say *"Phoenix, what are my notes?"* -> Phoenix reads out the real database record.

---

### 📅 DAY 5: Mark the Coder (Gemini 2.5 Pro Integration)
* **Goal**: Activate your technical developer agent using free Jio Gemini Pro.
* **Tasks**:
  1. Plug Gemini 2.5 Pro API key into the backend.
  2. Give Mark real filesystem tools (`read_file`, `write_file`, `list_directory`).
  3. Create Mark's system prompt (Lead Software Engineer).
* **Definition of Done**:
  - Command: *"Mark, create a modern landing page for a dental clinic in `projects/dental/index.html`."*
  - Phoenix delegates to Mark -> Mark writes the real HTML/CSS files on disk.

---

### 📅 DAY 6: The Sharks & The Hunter (Agency Business & Leads)
* **Goal**: Activate agency strategy audits and free live web research.
* **Tasks**:
  1. Implement **The Sharks** persona (devil's advocate critique of pricing, proposals, and margins).
  2. Implement **The Hunter** using `duckduckgo-search` (100% free web search).
* **Definition of Done**:
  - Tell Phoenix: *"Sharks, audit this: I want to charge ₹1.5L for an agency web app."* -> Sharks ruthlessly analyze the risks.
  - Tell Phoenix: *"Hunter, search for top digital marketing trends in 2026."* -> Returns verified live web facts.

---

### 📅 DAY 7: The Telegram Remote Gateway & Final Integration
* **Goal**: The College-to-Home superpower. Talk to Phoenix from your phone while outside.
* **Tasks**:
  1. Connect Python Telegram Bot (`python-telegram-bot` long-polling, 0 port forwarding).
  2. Send voice note or text from phone Telegram -> Phoenix processes it via Groq/Gemini -> Replies to phone.
  3. Full system smoke test.
* **Definition of Done**:
  - Send Telegram message from phone: *"Phoenix, add to-do: review Mark's code tonight."* -> Phoenix confirms on Telegram -> Visible on laptop screen when you sit at desk.

---

## 🔒 COMMITMENT CONTRACT:
* No new libraries outside this list.
* No rabbit holes into 3D animations or complex math.
* Execute 1 Day at a time.
