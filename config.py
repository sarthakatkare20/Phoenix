"""
Configuration for Paaro Realtime Voice System.
Handles audio capture settings, Silero VAD thresholds, server ports, and security flags.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class PaaroSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # VAD Configuration
    VAD_ENABLED: bool = True
    VAD_THRESHOLD: float = 0.5  # Probability threshold to consider frame as speech (0.0 - 1.0)
    VAD_SPEECH_START_CONFIRMATION: int = 3  # Number of consecutive speech frames to confirm SPEECH_START (~96ms at 32ms/frame)
    VAD_SILENCE_DURATION: float = 0.6  # Silence duration in seconds to trigger SPEECH_END (e.g. 600ms)
    
    # Audio Capture Configuration
    AUDIO_SAMPLE_RATE: int = 16000  # 16 kHz mono (native for Silero VAD and Whisper)
    AUDIO_CHANNELS: int = 1         # Mono
    AUDIO_FRAME_MS: int = 32        # Frame duration in milliseconds (32ms = 512 samples at 16kHz)
    AUDIO_FRAME_SAMPLES: int = 512  # Number of samples per frame
    AUDIO_DEVICE_INDEX: Optional[int] = None  # None for default system microphone

    # Speech-to-Text (STT) Configuration (faster-whisper)
    STT_ENABLED: bool = True
    WHISPER_MODEL_SIZE: str = "base"  # "tiny", "base", "small", "medium"
    WHISPER_DEVICE: str = "cpu"       # "cpu" or "cuda"
    WHISPER_COMPUTE_TYPE: str = "int8" # "int8", "float16", "float32"
    STT_UPDATE_INTERVAL: float = 0.4  # Incremental partial transcription interval in seconds (~400ms)
    STT_LANGUAGE: Optional[str] = None # Auto-detect English, Hindi, Hinglish
    WHISPER_BEAM_SIZE: int = 1        # Beam size for fast decoding (1 = greedy)
    WHISPER_TEMPERATURE: float = 0.0  # Temperature for decoding
    WHISPER_CONDITION_ON_PREVIOUS_TEXT: bool = False  # Avoid hallucinations
    WHISPER_NO_SPEECH_THRESHOLD: float = 0.6  # Probability threshold for no speech
    STT_MIN_AUDIO_DURATION: float = 0.5  # Minimum seconds of audio to attempt transcription (ignores micro-noises)

    # Sarvam AI Saaras STT Configuration (Indian Accents & Code-Mixed Hinglish)
    SARVAM_API_KEY: Optional[str] = None
    SARVAM_STT_MODEL: str = "saaras:v4"
    SARVAM_STT_MODE: str = "codemix"  # "codemix", "transcribe", "translit"
    SARVAM_LANGUAGE_CODE: str = "hi-IN"

    # Large Language Model (LLM) Configuration (Gemini / Groq / Ollama)
    LLM_ENABLED: bool = True
    LLM_PROVIDER: str = "auto"  # "auto", "gemini", "groq", "ollama"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    OLLAMA_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3.2:3b"  # "llama3.2:3b", "hermes3:latest"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 250
    LLM_STREAM_BUFFER_MS: float = 30.0  # Delta buffering duration in milliseconds
    LLM_SYSTEM_PROMPT: str = (
        "You are PHOENIX, an ultra-crisp, highly capable AI assistant, mission control, and agency operating system. "
        "Keep spoken voice answers direct, natural, and under 40 words unless asked for more. "
        "Do not use markdown, code blocks, or emojis in spoken replies. "
        "Bilingual fluency: If the user speaks in Hindi or Hinglish, reply in natural, respectful Hinglish. "
        "If the user speaks in English, reply in English. "
        "AUTONOMOUS AGENT CAPABILITIES: You have an autonomous execution engine named HERMES equipped with full terminal execution, code writing, multi-file project creation, and web search capabilities. "
        "When the user asks you to write code, build a project, create or modify files, conduct technical research, or run terminal tasks, reply with a concise spoken confirmation and trigger Hermes using: "
        "[ACTION: {\"type\": \"hermes_task\", \"query\": \"<exact detailed task description for Hermes>\"}]. "
        "PHONE CALLING: When the user asks you to call their phone, call them, or wake them up via phone call, reply briefly (e.g. 'Calling you now, sir.') and trigger: "
        "[ACTION: {\"type\": \"make_phone_call\", \"message\": \"<message to speak when user answers call>\"}]. "
        "VISUAL SCREEN AUTOMATION & ANTIGRAVITY: "
        "When the user asks you to write code in Antigravity or ask/prompt Antigravity, reply briefly (e.g. 'Bringing up Antigravity now, sir.') and trigger: "
        "[ACTION: {\"type\": \"send_to_antigravity\", \"prompt\": \"<detailed coding prompt to type into Antigravity>\"}]. "
        "When the user asks to open Chrome, search Google, or view a website visibly on screen, reply briefly and trigger: "
        "[ACTION: {\"type\": \"open_chrome\", \"target\": \"<url or search query>\"}]. "
        "TOTAL VISIBILITY & TRANSPARENCY POLICY: You are a transparent, visual mission control assistant. Never perform actions secretly or in the dark. Always announce what you are doing verbally before executing. When searching the web or opening links, always launch Chrome visibly on screen using open_chrome so the user can watch the page. When coding, bring up Antigravity using send_to_antigravity so the user sees the IDE and prompt live. For other system apps, use [ACTION: {\"type\": \"open_app\", \"target\": \"<app>\"}]. The user must always see everything happening on screen."
    )

    # Text-to-Speech (TTS) Configuration (Kokoro / Local Synthesis)
    # Set to False on backend to prevent dual/duplicate voice clash with Browser UI
    TTS_ENABLED: bool = False
    TTS_ENGINE: str = "kokoro"  # "kokoro", "pyttsx3", "mock"
    TTS_VOICE: str = "bm_george" # Kokoro voices: "bm_george" (British Male Jarvis), "am_adam", "af_sarah"
    TTS_SPEED: float = 1.0
    TTS_SAMPLE_RATE: int = 24000  # 24kHz for Kokoro
    TTS_CHUNK_MIN_CHARS: int = 20  # Minimum characters before soft punctuation chunking
    TTS_CHUNK_MAX_CHARS: int = 140 # Maximum characters before forcing word boundary split
    TTS_QUEUE_MAX_SIZE: int = 20   # Maximum queued audio chunks

    # Barge-In & Interruption Configuration
    BARGE_IN_ENABLED: bool = True
    BARGE_IN_THRESHOLD: float = 0.85  # Elevated VAD probability threshold during TTS playback (echo guard)
    BARGE_IN_CONFIRMATION_FRAMES: int = 8  # Consecutive frames to confirm interruption (~256ms at 32ms/frame)
    BARGE_IN_GRACE_PERIOD_MS: float = 300.0  # Initial playback grace period to ignore speaker pop
    BARGE_IN_MIN_ENERGY: float = 0.04  # Minimum RMS energy required during playback to trigger barge-in

    # Conversation Context & Memory Configuration
    MEMORY_ENABLED: bool = True
    MEMORY_DB_PATH: str = "data/paaro_memory.db"
    CONVERSATION_MAX_TURNS: int = 10  # Maximum recent conversation turns included in context
    CONTEXT_MAX_TOKENS: int = 2000    # Budget for assembled prompt and conversation history
    MEMORY_MAX_RESULTS: int = 5       # Max long-term memories injected into prompt
    DEFAULT_USER_ID: str = "sarthak"  # Local default user identity

    # Proactive Intelligence & Action Engine (Step 7)
    PROACTIVE_ENABLED: bool = True
    PROACTIVE_MIN_SEVERITY: str = "low"  # "low", "medium", "high", "critical"
    PROACTIVE_QUEUE_SIZE: int = 20       # Max bounded deferred event queue size
    PROACTIVE_MAX_EVENTS_PER_WINDOW: int = 10
    PROACTIVE_DEFAULT_COOLDOWN_SEC: float = 60.0
    PROACTIVE_AUTO_SPEECH: bool = True   # Automatically vocalize NOTIFY / ASK decisions via TTS

    # Reasoning & Planning Engine (Step 8)
    REASONING_ENABLED: bool = True
    MAX_PLAN_STEPS: int = 8
    MAX_REPLANS: int = 3
    MAX_RETRIES_PER_STEP: int = 2
    REASONING_TIMEOUT_SEC: float = 60.0

    # Basic Computer Control (Step 9)
    COMPUTER_CONTROL_ENABLED: bool = True
    COMPUTER_CONTROL_CONFIRM_SENSITIVE: bool = True
    COMPUTER_CONTROL_ALLOWED_ROOTS: List[str] = [
        "F:\\jarvis",
        "C:\\Users\\sarth",
    ]
    COMPUTER_CONTROL_MAX_PROCESS_LIST: int = 50
    COMPUTER_CONTROL_VERIFICATION_TIMEOUT_SEC: float = 3.0

    # Server & Networking
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    WEBSOCKET_PING_INTERVAL: int = 20
    WEBSOCKET_PING_TIMEOUT: int = 20

    # Security & Emergency Control
    EMERGENCY_STOP_ENABLED: bool = False
    REQUIRE_CONFIRMATION_ON_RESTART: bool = False

    # Telephony & Outbound Voice Calling (Twilio)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None
    USER_PHONE_NUMBER: Optional[str] = None


# Global settings singleton
settings = PaaroSettings()


