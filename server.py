"""
FastAPI Server & WebSocket Hub for Paaro Realtime Voice.
Exposes realtime VAD events, status endpoints, and emergency control.
"""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
from typing import Any, Dict, List, Optional, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from security import security_context
from realtime_pipeline import RealtimeVoicePipeline
from reasoning import ExecutionPlan, PlanStep, TaskComplexity
from tool_gateway import tool_gateway, PolicyDecision
from computer import (
    computer_controller,
    ComputerAction,
    ComputerActionType,
    ComputerActionResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("paaro.server")

# Global pipeline instance
pipeline: Optional[RealtimeVoicePipeline] = None


class ConnectionManager:
    """Manages active WebSocket connections and thread-safe async broadcast."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("Client connected. Total active connections: %d", len(self.active_connections))
        # Send initial state
        initial_event = {
            "type": "connection_ack",
            "vad_enabled": settings.VAD_ENABLED,
            "emergency_stop": security_context.is_emergency_stopped,
            "state": pipeline.current_state.value if pipeline else "unknown",
        }
        await websocket.send_text(json.dumps(initial_event))

        # Send Bridge-compatible ready frame so the HUD links all systems!
        ready_event = {
            "type": "ready",
            "servers": [
                "phoenix-core",
                "gemini-3.5-flash-lite",
                "faster-whisper (stt)",
                "kokoro (tts)",
                "system-telemetry",
                "tool-gateway",
            ],
        }
        await websocket.send_text(json.dumps(ready_event))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info("Client disconnected. Remaining connections: %d", len(self.active_connections))

    async def broadcast_async(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.active_connections.discard(dead)

    def broadcast_threadsafe(self, message: dict):
        """Thread-safe event broadcast from background audio thread to async loop."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast_async(message), self._loop)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    loop = asyncio.get_running_loop()
    manager.set_loop(loop)

    logger.info("Initializing Paaro Realtime Voice Pipeline...")
    pipeline = RealtimeVoicePipeline(config=settings, security=security_context)
    pipeline.set_async_loop(loop)
    
    # Forward pipeline events to WebSocket clients thread-safely
    pipeline.add_event_listener(manager.broadcast_threadsafe)

    if settings.VAD_ENABLED:
        try:
            pipeline.start()
        except Exception as e:
            logger.warning("Could not auto-start audio capture (may be in test or headless environment): %s", e)

    yield

    logger.info("Shutting down Paaro Realtime Voice Pipeline...")
    if pipeline:
        pipeline.stop()


app = FastAPI(
    title="Paaro Realtime Voice API",
    description="Realtime Voice Activity Detection, Streaming STT and Streaming LLM for Paaro",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from memory.models import MemoryCategory

# REST Models
class EmergencyStopRequest(BaseModel):
    stopped: bool
    reason: Optional[str] = None


class VadConfigRequest(BaseModel):
    threshold: Optional[float] = None
    speech_start_confirmation: Optional[int] = None
    silence_duration: Optional[float] = None


class SttConfigRequest(BaseModel):
    update_interval: Optional[float] = None
    language: Optional[str] = None
    beam_size: Optional[int] = None
    temperature: Optional[float] = None


class LlmConfigRequest(BaseModel):
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream_buffer_ms: Optional[float] = None
    system_prompt: Optional[str] = None


class TtsConfigRequest(BaseModel):
    engine: Optional[str] = None
    voice: Optional[str] = None
    speed: Optional[float] = None
    chunk_min_chars: Optional[int] = None
    chunk_max_chars: Optional[int] = None


class TtsSpeakRequest(BaseModel):
    text: str


class BargeInConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    threshold: Optional[float] = None
    confirmation_frames: Optional[int] = None
    grace_period_ms: Optional[float] = None
    min_energy: Optional[float] = None


class ToolConfirmRequest(BaseModel):
    call_id: str
    approved: bool


class MemoryCreateRequest(BaseModel):
    content: str
    category: Optional[str] = "preference"
    importance: Optional[float] = 0.5
    confidence: Optional[float] = 1.0
    user_id: Optional[str] = None


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    importance: Optional[float] = None
    confidence: Optional[float] = None


class ProactiveEventRequest(BaseModel):
    event_type: str
    source: Optional[str] = "api"
    severity: Optional[str] = "low"
    data: Optional[Dict[str, Any]] = None
    ttl_seconds: Optional[float] = 300.0
    requires_llm: Optional[bool] = False


class ProactiveConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    min_severity: Optional[str] = None
    auto_speech: Optional[bool] = None
    cooldowns: Optional[Dict[str, float]] = None


class TaskClassificationRequest(BaseModel):
    query: str


class PlanGenerationRequest(BaseModel):
    goal: str
    session_id: Optional[str] = None


class PlanExecutionRequest(BaseModel):
    goal: Optional[str] = None
    plan: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


class ReasoningConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    max_steps: Optional[int] = None
    max_replans: Optional[int] = None
    max_retries_per_step: Optional[int] = None


@app.get("/health")
async def health_check():
    return {
        "ok": True,
        "status": "ok",
        "stt": bool(pipeline and pipeline.stt),
        "tts": bool(pipeline and pipeline.tts),
        "pipeline_running": pipeline.is_running if pipeline else False,
        "vad_state": pipeline.current_state.value if pipeline else "unknown",
        "stt_enabled": bool(pipeline and pipeline.stt),
        "llm_enabled": bool(pipeline and pipeline.llm),
        "tts_enabled": bool(pipeline and pipeline.tts),
        "barge_in_enabled": settings.BARGE_IN_ENABLED,
        "proactive_enabled": bool(pipeline and pipeline.proactive),
        "reasoning_enabled": bool(pipeline and pipeline.reasoning),
        "emergency_stopped": security_context.is_emergency_stopped,
    }


@app.get("/api/vad/status")
async def get_vad_status():
    return {
        "is_running": pipeline.is_running if pipeline else False,
        "current_state": pipeline.current_state.value if pipeline else "unknown",
        "emergency_stopped": security_context.is_emergency_stopped,
        "halt_reason": security_context.halt_reason,
        "config": {
            "vad_enabled": settings.VAD_ENABLED,
            "threshold": pipeline.vad.threshold if pipeline else settings.VAD_THRESHOLD,
            "speech_start_confirmation": pipeline.state_machine.speech_start_confirmation if pipeline else settings.VAD_SPEECH_START_CONFIRMATION,
            "silence_duration": pipeline.state_machine.silence_duration_sec if pipeline else settings.VAD_SILENCE_DURATION,
            "sample_rate": settings.AUDIO_SAMPLE_RATE,
            "frame_ms": settings.AUDIO_FRAME_MS,
        },
    }


@app.get("/api/stats")
async def get_system_stats():
    import psutil
    import time
    vm = psutil.virtual_memory()
    bat = psutil.sensors_battery()
    return {
        "cpuPercent": round(psutil.cpu_percent(interval=None) or 15.0, 1),
        "ramPercent": round(vm.percent, 1),
        "ramUsedGb": f"{vm.used / (1024**3):.1f}",
        "ramTotalGb": f"{vm.total / (1024**3):.1f}",
        "uptimeMinutes": int((time.time() - psutil.boot_time()) / 60),
        "batteryPercent": round(bat.percent) if bat else None,
        "isCharging": bat.power_plugged if bat else None,
    }


@app.get("/api/stt/status")
async def get_stt_status():
    stt_active = bool(pipeline and pipeline.stt)
    return {
        "stt_enabled": stt_active,
        "model_size": settings.WHISPER_MODEL_SIZE,
        "device": settings.WHISPER_DEVICE,
        "compute_type": settings.WHISPER_COMPUTE_TYPE,
        "update_interval": settings.STT_UPDATE_INTERVAL,
        "language": settings.STT_LANGUAGE,
        "beam_size": settings.WHISPER_BEAM_SIZE,
    }


@app.post("/api/stt/config")
async def update_stt_config(cfg: SttConfigRequest):
    if not pipeline or not pipeline.stt:
        raise HTTPException(status_code=500, detail="STT not initialized")

    if cfg.update_interval is not None:
        pipeline.config.STT_UPDATE_INTERVAL = max(0.1, cfg.update_interval)
    if cfg.language is not None:
        pipeline.config.STT_LANGUAGE = cfg.language if cfg.language != "auto" else None
    if cfg.beam_size is not None:
        pipeline.config.WHISPER_BEAM_SIZE = max(1, cfg.beam_size)
    if cfg.temperature is not None:
        pipeline.config.WHISPER_TEMPERATURE = max(0.0, cfg.temperature)

    return {
        "status": "updated",
        "update_interval": pipeline.config.STT_UPDATE_INTERVAL,
        "language": pipeline.config.STT_LANGUAGE,
        "beam_size": pipeline.config.WHISPER_BEAM_SIZE,
        "temperature": pipeline.config.WHISPER_TEMPERATURE,
    }


@app.post("/api/vad/start")
async def start_vad():
    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")
    if security_context.is_emergency_stopped:
        raise HTTPException(status_code=403, detail="Cannot start: Emergency stop is active")
    pipeline.start()
    return {"status": "started", "state": pipeline.current_state.value}


@app.post("/api/vad/stop")
async def stop_vad():
    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")
    pipeline.stop()
    return {"status": "stopped", "state": pipeline.current_state.value}


@app.post("/api/vad/config")
async def update_vad_config(cfg: VadConfigRequest):
    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")

    if cfg.threshold is not None:
        pipeline.vad.threshold = max(0.01, min(0.99, cfg.threshold))
    if cfg.speech_start_confirmation is not None:
        pipeline.state_machine.speech_start_confirmation = max(1, cfg.speech_start_confirmation)
    if cfg.silence_duration is not None:
        pipeline.state_machine.silence_duration_sec = max(0.1, cfg.silence_duration)

    return {
        "status": "updated",
        "threshold": pipeline.vad.threshold,
        "speech_start_confirmation": pipeline.state_machine.speech_start_confirmation,
        "silence_duration": pipeline.state_machine.silence_duration_sec,
    }


@app.get("/api/llm/status")
async def get_llm_status():
    llm_active = bool(pipeline and pipeline.llm)
    provider, active_model = pipeline.llm.get_active_provider() if (pipeline and pipeline.llm) else ("none", "none")
    return {
        "llm_enabled": llm_active,
        "provider": provider,
        "model": active_model,
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "stream_buffer_ms": settings.LLM_STREAM_BUFFER_MS,
    }


@app.post("/api/llm/config")
async def update_llm_config(cfg: LlmConfigRequest):
    if not pipeline or not pipeline.llm:
        raise HTTPException(status_code=500, detail="LLM not initialized")

    if cfg.model is not None:
        pipeline.config.LLM_MODEL = cfg.model
    if cfg.temperature is not None:
        pipeline.config.LLM_TEMPERATURE = max(0.0, min(1.5, cfg.temperature))
    if cfg.max_tokens is not None:
        pipeline.config.LLM_MAX_TOKENS = max(10, cfg.max_tokens)
    if cfg.stream_buffer_ms is not None:
        pipeline.config.LLM_STREAM_BUFFER_MS = max(5.0, cfg.stream_buffer_ms)
    if cfg.system_prompt is not None:
        pipeline.config.LLM_SYSTEM_PROMPT = cfg.system_prompt

    return {
        "status": "updated",
        "model": pipeline.config.LLM_MODEL,
        "temperature": pipeline.config.LLM_TEMPERATURE,
        "max_tokens": pipeline.config.LLM_MAX_TOKENS,
        "stream_buffer_ms": pipeline.config.LLM_STREAM_BUFFER_MS,
    }


@app.get("/api/tts/status")
async def get_tts_status():
    tts_active = bool(pipeline and pipeline.tts)
    metrics = pipeline.tts.get_metrics() if pipeline and pipeline.tts else {}
    return {
        "tts_enabled": tts_active,
        "engine": settings.TTS_ENGINE,
        "voice": settings.TTS_VOICE,
        "speed": settings.TTS_SPEED,
        "sample_rate": settings.TTS_SAMPLE_RATE,
        "chunk_min_chars": settings.TTS_CHUNK_MIN_CHARS,
        "chunk_max_chars": settings.TTS_CHUNK_MAX_CHARS,
        "queue_max_size": settings.TTS_QUEUE_MAX_SIZE,
        "metrics": metrics,
    }


@app.post("/api/tts/config")
async def update_tts_config(cfg: TtsConfigRequest):
    if not pipeline or not pipeline.tts:
        raise HTTPException(status_code=500, detail="TTS not initialized")

    if cfg.engine is not None:
        pipeline.config.TTS_ENGINE = cfg.engine
    if cfg.voice is not None:
        pipeline.config.TTS_VOICE = cfg.voice
        if hasattr(pipeline.tts.backend, "voice"):
            pipeline.tts.backend.voice = cfg.voice
    if cfg.speed is not None:
        pipeline.config.TTS_SPEED = max(0.5, min(2.0, cfg.speed))
        if hasattr(pipeline.tts.backend, "speed"):
            pipeline.tts.backend.speed = pipeline.config.TTS_SPEED
    if cfg.chunk_min_chars is not None:
        pipeline.config.TTS_CHUNK_MIN_CHARS = max(5, cfg.chunk_min_chars)
        pipeline.tts.chunker.min_chars = pipeline.config.TTS_CHUNK_MIN_CHARS
    if cfg.chunk_max_chars is not None:
        pipeline.config.TTS_CHUNK_MAX_CHARS = max(20, cfg.chunk_max_chars)
        pipeline.tts.chunker.max_chars = pipeline.config.TTS_CHUNK_MAX_CHARS

    return {
        "status": "updated",
        "engine": pipeline.config.TTS_ENGINE,
        "voice": pipeline.config.TTS_VOICE,
        "speed": pipeline.config.TTS_SPEED,
        "chunk_min_chars": pipeline.config.TTS_CHUNK_MIN_CHARS,
        "chunk_max_chars": pipeline.config.TTS_CHUNK_MAX_CHARS,
    }


@app.post("/api/tts/cancel")
async def cancel_tts():
    if not pipeline or not pipeline.tts:
        raise HTTPException(status_code=500, detail="TTS not initialized")
    pipeline.tts.cancel()
    return {"status": "cancelled"}


@app.post("/api/tts/speak")
async def speak_text(req: TtsSpeakRequest):
    if not pipeline or not pipeline.tts:
        raise HTTPException(status_code=500, detail="TTS not initialized")
    if security_context.is_emergency_stopped:
        raise HTTPException(status_code=403, detail="Cannot speak: Emergency stop is active")

    pipeline.tts.on_llm_start()
    pipeline.tts.feed_text_delta(req.text)
    pipeline.tts.flush_text()
    return {"status": "queued", "text": req.text}


@app.get("/api/barge-in/status")
async def get_barge_in_status():
    metrics = pipeline.get_barge_in_metrics() if pipeline else {}
    return {
        "barge_in_enabled": settings.BARGE_IN_ENABLED,
        "barge_in_threshold": settings.BARGE_IN_THRESHOLD,
        "confirmation_frames": settings.BARGE_IN_CONFIRMATION_FRAMES,
        "grace_period_ms": settings.BARGE_IN_GRACE_PERIOD_MS,
        "min_energy": settings.BARGE_IN_MIN_ENERGY,
        "is_assistant_speaking": pipeline.is_assistant_speaking if pipeline else False,
        "metrics": metrics,
    }


@app.post("/api/barge-in/config")
async def update_barge_in_config(cfg: BargeInConfigRequest):
    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")

    if cfg.enabled is not None:
        pipeline.config.BARGE_IN_ENABLED = cfg.enabled
    if cfg.threshold is not None:
        pipeline.config.BARGE_IN_THRESHOLD = max(0.01, min(0.99, cfg.threshold))
    if cfg.confirmation_frames is not None:
        pipeline.config.BARGE_IN_CONFIRMATION_FRAMES = max(1, cfg.confirmation_frames)
    if cfg.grace_period_ms is not None:
        pipeline.config.BARGE_IN_GRACE_PERIOD_MS = max(0.0, cfg.grace_period_ms)
    if cfg.min_energy is not None:
        pipeline.config.BARGE_IN_MIN_ENERGY = max(0.0, cfg.min_energy)

    return {
        "status": "updated",
        "barge_in_enabled": pipeline.config.BARGE_IN_ENABLED,
        "threshold": pipeline.config.BARGE_IN_THRESHOLD,
        "confirmation_frames": pipeline.config.BARGE_IN_CONFIRMATION_FRAMES,
        "grace_period_ms": pipeline.config.BARGE_IN_GRACE_PERIOD_MS,
        "min_energy": pipeline.config.BARGE_IN_MIN_ENERGY,
    }


@app.post("/api/tools/confirm")
async def confirm_tool_execution(req: ToolConfirmRequest):
    if not pipeline or not pipeline.llm:
        raise HTTPException(status_code=500, detail="LLM / Tool gateway not initialized")

    res = pipeline.llm.gateway.resolve_confirmation(req.call_id, req.approved)
    # Broadcast confirmation resolution event
    await manager.broadcast_async({
        "type": "llm",
        "status": "tool_confirmation_resolved",
        "call_id": req.call_id,
        "approved": req.approved,
        "result": res,
    })
    return res


@app.post("/api/emergency-stop")
async def set_emergency_stop(req: EmergencyStopRequest):
    if req.stopped:
        security_context.trigger_emergency_stop(req.reason or "Triggered via API")
    else:
        security_context.clear_emergency_stop(req.reason or "Cleared via API")
    return {
        "emergency_stopped": security_context.is_emergency_stopped,
        "reason": security_context.halt_reason,
    }


# -------------------------------------------------------------------------
# Memory & Session REST Endpoints (Step 6)
# -------------------------------------------------------------------------

@app.get("/api/memory")
async def list_memories(user_id: Optional[str] = None, category: Optional[str] = None):
    """List stored persistent memories with optional filtering."""
    if not pipeline or not pipeline.memory_service:
        return {"memories": [], "count": 0, "status": "memory_disabled"}

    cat_enum = None
    if category:
        try:
            cat_enum = MemoryCategory(category.lower())
        except ValueError:
            pass

    memories = pipeline.memory_service.list_all_memories(user_id=user_id, category=cat_enum)
    return {
        "memories": [m.to_dict() for m in memories],
        "count": len(memories),
        "status": "ok",
    }


@app.post("/api/memory")
async def create_or_update_memory(req: MemoryCreateRequest):
    """Explicitly store or update a memory record."""
    if not pipeline or not pipeline.memory_service:
        raise HTTPException(status_code=500, detail="Memory service not initialized")

    try:
        cat_enum = MemoryCategory(req.category.lower()) if req.category else MemoryCategory.PREFERENCE
    except ValueError:
        cat_enum = MemoryCategory.PREFERENCE

    mem, is_new = pipeline.memory_service.store_memory(
        content=req.content,
        category=cat_enum,
        user_id=req.user_id,
        importance=req.importance or 0.5,
        confidence=req.confidence or 1.0,
        source="user_explicit",
    )
    return {
        "status": "created" if is_new else "deduplicated",
        "memory": mem.to_dict(),
    }


@app.get("/api/memory/search")
async def search_memories(q: str, user_id: Optional[str] = None, limit: int = 5):
    """Deterministic relevance search across memories."""
    if not pipeline or not pipeline.memory_service:
        return {"results": [], "query": q, "status": "memory_disabled"}

    results = pipeline.memory_service.search_memories(
        query=q,
        user_id=user_id,
        top_k=max(1, min(20, limit)),
    )
    return {
        "query": q,
        "results": [{"memory": mem.to_dict(), "score": round(score, 3)} for mem, score in results],
        "count": len(results),
        "status": "ok",
    }


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a memory record by ID."""
    if not pipeline or not pipeline.memory_service:
        raise HTTPException(status_code=500, detail="Memory service not initialized")

    deleted = pipeline.memory_service.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "deleted", "memory_id": memory_id}


@app.get("/api/session/current")
async def get_current_session():
    """Retrieve active session details and recent conversation turns."""
    if not pipeline or not pipeline.memory_service:
        return {"session": None, "turns": [], "status": "memory_disabled"}

    session = pipeline.memory_service.get_or_create_active_session()
    turns = pipeline.memory_service.get_recent_turns(session.id, limit=20)
    return {
        "session": session.to_dict(),
        "turns": [t.to_dict() for t in turns],
        "status": "ok",
    }


@app.post("/api/session/new")
async def create_new_session(user_id: Optional[str] = None):
    """Start a fresh conversation session."""
    if not pipeline or not pipeline.memory_service:
        raise HTTPException(status_code=500, detail="Memory service not initialized")

    session = pipeline.memory_service.create_new_session(user_id=user_id)
    pipeline.active_session_id = session.id
    return {"status": "created", "session": session.to_dict()}


# -------------------------------------------------------------------------
# Proactive Intelligence & Action Engine Endpoints (Step 7)
# -------------------------------------------------------------------------

from proactive.events import EventSeverity, ProactiveEvent

@app.post("/api/proactive/event")
async def emit_proactive_event(req: ProactiveEventRequest):
    """Publish and evaluate a proactive background event."""
    if not pipeline or not pipeline.proactive:
        raise HTTPException(status_code=500, detail="Proactive engine not initialized")

    sev = EventSeverity.LOW
    try:
        sev = EventSeverity(req.severity.lower()) if req.severity else EventSeverity.LOW
    except Exception:
        pass

    event = ProactiveEvent(
        event_type=req.event_type,
        source=req.source or "api",
        severity=sev,
        data=req.data or {},
        ttl_seconds=req.ttl_seconds or 300.0,
        requires_llm=bool(req.requires_llm),
    )

    user_state = pipeline.get_user_activity_state()
    decision = await pipeline.proactive.brain.process_event(
        event=event,
        user_state=user_state,
        session_id=pipeline.active_session_id,
    )
    return {
        "status": "processed",
        "decision": decision.to_dict(),
        "user_state": user_state.value,
    }


@app.get("/api/proactive/status")
async def get_proactive_status():
    """Retrieve current proactive engine metrics, queue status, and active state."""
    if not pipeline or not pipeline.proactive:
        return {"status": "disabled", "enabled": False}

    return {
        "status": "active",
        "enabled": settings.PROACTIVE_ENABLED,
        "min_severity": settings.PROACTIVE_MIN_SEVERITY,
        "auto_speech": settings.PROACTIVE_AUTO_SPEECH,
        "user_state": pipeline.get_user_activity_state().value,
        "queue_depth": len(pipeline.proactive.queue),
        "cooldowns": pipeline.proactive.evaluator.cooldowns,
    }


@app.post("/api/proactive/config")
async def update_proactive_config(cfg: ProactiveConfigRequest):
    """Update proactive engine parameters at runtime."""
    if not pipeline or not pipeline.proactive:
        raise HTTPException(status_code=500, detail="Proactive engine not initialized")

    if cfg.enabled is not None:
        pipeline.config.PROACTIVE_ENABLED = cfg.enabled
    if cfg.min_severity is not None:
        try:
            sev = EventSeverity(cfg.min_severity.lower())
            pipeline.config.PROACTIVE_MIN_SEVERITY = sev.value
            pipeline.proactive.evaluator.min_severity = sev
        except Exception:
            pass
    if cfg.auto_speech is not None:
        pipeline.config.PROACTIVE_AUTO_SPEECH = cfg.auto_speech
        pipeline.proactive.brain.auto_speech = cfg.auto_speech
    if cfg.cooldowns:
        for k, v in cfg.cooldowns.items():
            pipeline.proactive.evaluator.set_cooldown(k, v)

    return {
        "status": "updated",
        "enabled": pipeline.config.PROACTIVE_ENABLED,
        "min_severity": pipeline.config.PROACTIVE_MIN_SEVERITY,
        "auto_speech": pipeline.config.PROACTIVE_AUTO_SPEECH,
        "cooldowns": pipeline.proactive.evaluator.cooldowns,
    }


@app.get("/api/proactive/queue")
async def get_proactive_queue():
    """List all currently queued deferred proactive events."""
    if not pipeline or not pipeline.proactive:
        return {"queue": [], "count": 0}

    items = pipeline.proactive.queue.to_list()
    return {"queue": items, "count": len(items)}


@app.post("/api/proactive/queue/clear")
async def clear_proactive_queue():
    """Clear all queued deferred proactive events."""
    if not pipeline or not pipeline.proactive:
        raise HTTPException(status_code=500, detail="Proactive engine not initialized")

    pipeline.proactive.queue.clear()
    return {"status": "cleared", "queue_depth": 0}


# ---------------------------------------------------------------------------
# Step 8: Reasoning & Planning Engine REST Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/reasoning/classify")
async def classify_task_complexity(req: TaskClassificationRequest):
    """Classify user query complexity into DIRECT, SIMPLE, MULTI_STEP, or COMPLEX."""
    if not pipeline or not pipeline.reasoning:
        raise HTTPException(status_code=500, detail="Reasoning engine not initialized")

    complexity = await pipeline.reasoning.classifier.classify(req.query)
    return {
        "query": req.query,
        "complexity": complexity.value,
        "fast_path": complexity.is_fast_path,
    }


@app.post("/api/reasoning/plan")
async def generate_reasoning_plan(req: PlanGenerationRequest):
    """Generate and validate a structured multi-step execution plan."""
    if not pipeline or not pipeline.reasoning:
        raise HTTPException(status_code=500, detail="Reasoning engine not initialized")

    plan = await pipeline.reasoning.generate_plan(req.goal, session_id=req.session_id)
    if not plan:
        raise HTTPException(status_code=400, detail="Could not generate valid plan for given goal")
    return plan.to_dict()


@app.post("/api/reasoning/execute")
async def execute_reasoning_plan(req: PlanExecutionRequest):
    """Execute a structured plan or generate and execute one from a goal."""
    if not pipeline or not pipeline.reasoning:
        raise HTTPException(status_code=500, detail="Reasoning engine not initialized")

    if req.plan:
        plan = ExecutionPlan.from_dict(req.plan)
        valid, errors = pipeline.reasoning.validator.validate(plan)
        if not valid:
            raise HTTPException(status_code=400, detail=f"Invalid plan: {'; '.join(errors)}")
        executed_plan = await pipeline.reasoning.executor.execute_plan(plan)
        return executed_plan.to_dict()
    elif req.goal:
        plan = await pipeline.reasoning.execute_task(req.goal, session_id=req.session_id)
        if not plan:
            raise HTTPException(status_code=500, detail="Failed to execute reasoning task")
        return plan.to_dict()
    else:
        raise HTTPException(status_code=400, detail="Must provide either 'goal' or 'plan'")


@app.get("/api/reasoning/plan/current")
async def get_current_reasoning_plan():
    """Get the currently executing plan, if any."""
    if not pipeline or not pipeline.reasoning:
        return {"active": False, "plan": None}

    plan = pipeline.reasoning.executor.active_plan
    if not plan:
        return {"active": False, "plan": None}
    return {"active": True, "plan": plan.to_dict()}


@app.post("/api/reasoning/plan/cancel")
async def cancel_current_reasoning_plan():
    """Cancel the currently running plan."""
    if not pipeline or not pipeline.reasoning:
        raise HTTPException(status_code=500, detail="Reasoning engine not initialized")

    cancelled = pipeline.reasoning.cancel_active_plan()
    return {"cancelled": cancelled}


@app.get("/api/reasoning/config")
async def get_reasoning_config():
    """Retrieve current reasoning engine settings."""
    if not pipeline or not pipeline.reasoning:
        return {
            "enabled": False,
            "max_steps": settings.MAX_PLAN_STEPS,
            "max_replans": settings.MAX_REPLANS,
            "max_retries_per_step": settings.MAX_RETRIES_PER_STEP,
        }
    return {
        "enabled": pipeline.config.REASONING_ENABLED,
        "max_steps": pipeline.config.MAX_PLAN_STEPS,
        "max_replans": pipeline.config.MAX_REPLANS,
        "max_retries_per_step": pipeline.config.MAX_RETRIES_PER_STEP,
        "timeout_sec": pipeline.config.REASONING_TIMEOUT_SEC,
    }


@app.post("/api/reasoning/config")
async def update_reasoning_config(cfg: ReasoningConfigRequest):
    """Update reasoning engine limits and settings at runtime."""
    if not pipeline or not pipeline.reasoning:
        raise HTTPException(status_code=500, detail="Reasoning engine not initialized")

    if cfg.enabled is not None:
        pipeline.config.REASONING_ENABLED = cfg.enabled
    if cfg.max_steps is not None:
        pipeline.config.MAX_PLAN_STEPS = cfg.max_steps
        pipeline.reasoning.validator.max_steps = cfg.max_steps
        pipeline.reasoning.planner.max_steps = cfg.max_steps
    if cfg.max_replans is not None:
        pipeline.config.MAX_REPLANS = cfg.max_replans
        pipeline.reasoning.replanner.max_replans = cfg.max_replans
    if cfg.max_retries_per_step is not None:
        pipeline.config.MAX_RETRIES_PER_STEP = cfg.max_retries_per_step
        pipeline.reasoning.executor.max_retries = cfg.max_retries_per_step

    return {
        "status": "updated",
        "enabled": pipeline.config.REASONING_ENABLED,
        "max_steps": pipeline.config.MAX_PLAN_STEPS,
        "max_replans": pipeline.config.MAX_REPLANS,
        "max_retries_per_step": pipeline.config.MAX_RETRIES_PER_STEP,
    }


# ===========================================================================
# Step 9 — Computer Control Endpoints
# ===========================================================================

class ComputerActionRequest(BaseModel):
    action: str
    target: str = ""
    args: Dict[str, Any] = {}
    verify: bool = True


class ComputerConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    confirm_sensitive: Optional[bool] = None
    allowed_roots: Optional[List[str]] = None
    max_process_list: Optional[int] = None


@app.post("/api/computer/action")
async def execute_computer_action(req: ComputerActionRequest):
    """
    Execute a structured computer control action through the ToolGateway and PolicyEngine.
    """
    if security_context.is_emergency_stopped:
        raise HTTPException(status_code=403, detail="System is emergency stopped.")

    if not settings.COMPUTER_CONTROL_ENABLED:
        raise HTTPException(status_code=403, detail="Computer control is disabled in configuration.")

    # Route through Tool Gateway
    gateway_args = dict(req.args)
    if req.target:
        gateway_args["target"] = req.target

    gw_res = tool_gateway.execute_allowed(req.action, gateway_args)
    return gw_res


@app.get("/api/computer/apps")
async def get_registered_apps():
    """List all registered desktop applications and their running status."""
    ctrl = pipeline.computer if pipeline and pipeline.computer else computer_controller
    apps = ctrl.apps.get_all_apps()
    return {"apps": [a.to_dict() for a in apps], "count": len(apps)}


@app.get("/api/computer/processes")
async def get_active_processes(max_count: int = 50, filter: Optional[str] = None):
    """List currently running processes on the system."""
    ctrl = pipeline.computer if pipeline and pipeline.computer else computer_controller
    procs = ctrl.get_process_list(max_count=max_count, filter_name=filter)
    return {"processes": [p.to_dict() for p in procs], "count": len(procs)}


@app.get("/api/computer/system")
async def get_computer_system_state():
    """Retrieve current OS metrics, active window, and resource usage."""
    ctrl = pipeline.computer if pipeline and pipeline.computer else computer_controller
    return {"system": ctrl.get_system_state()}


@app.get("/api/computer/config")
async def get_computer_config():
    """Retrieve computer control configuration."""
    return {
        "enabled": settings.COMPUTER_CONTROL_ENABLED,
        "confirm_sensitive": settings.COMPUTER_CONTROL_CONFIRM_SENSITIVE,
        "allowed_roots": settings.COMPUTER_CONTROL_ALLOWED_ROOTS,
        "max_process_list": settings.COMPUTER_CONTROL_MAX_PROCESS_LIST,
    }


@app.post("/api/computer/config")
async def update_computer_config(cfg: ComputerConfigRequest):
    """Update computer control configuration at runtime."""
    if cfg.enabled is not None:
        settings.COMPUTER_CONTROL_ENABLED = cfg.enabled
    if cfg.confirm_sensitive is not None:
        settings.COMPUTER_CONTROL_CONFIRM_SENSITIVE = cfg.confirm_sensitive
    if cfg.allowed_roots is not None:
        settings.COMPUTER_CONTROL_ALLOWED_ROOTS = cfg.allowed_roots
        ctrl = pipeline.computer if pipeline and pipeline.computer else computer_controller
        ctrl.filesystem.allowed_roots = [
            os.path.realpath(os.path.abspath(r)) for r in cfg.allowed_roots
        ]
    if cfg.max_process_list is not None:
        settings.COMPUTER_CONTROL_MAX_PROCESS_LIST = cfg.max_process_list

    return {
        "status": "updated",
        "enabled": settings.COMPUTER_CONTROL_ENABLED,
        "confirm_sensitive": settings.COMPUTER_CONTROL_CONFIRM_SENSITIVE,
        "allowed_roots": settings.COMPUTER_CONTROL_ALLOWED_ROOTS,
        "max_process_list": settings.COMPUTER_CONTROL_MAX_PROCESS_LIST,
    }


@app.websocket("/")
@app.websocket("/ws")
@app.websocket("/ws/vad")
@app.websocket("/api/vad/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
                action = data.get("action") or data.get("type")
                if action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif action == "ask":
                    prompt = data.get("text", "").strip()
                    ask_id = data.get("id", "a0")
                    if prompt and pipeline and pipeline.llm and not security_context.is_emergency_stopped:
                        async def handle_ask_stream(p: str, qid: str):
                            full_text = ""
                            try:
                                # Note: Browser UI manages its own TTS speaker and lip-sync with the 3D Arc Reactor.
                                # We stream tokens over WebSocket; do not duplicate speech on backend sounddevice.
                                async for event in pipeline.llm.stream_response(p, session_id=pipeline.active_session_id):
                                    st = event.get("status")
                                    if st == "delta":
                                        chunk = event.get("text", "")
                                        full_text += chunk
                                        await websocket.send_text(json.dumps({
                                            "type": "text",
                                            "delta": chunk,
                                            "ask": qid,
                                        }))
                                    elif st == "tool_request":
                                        await websocket.send_text(json.dumps({
                                            "type": "tool",
                                            "name": event.get("tool", ""),
                                            "ask": qid,
                                        }))
                                    elif st == "error":
                                        await websocket.send_text(json.dumps({
                                            "type": "error",
                                            "message": event.get("message", "Generation failed"),
                                            "ask": qid,
                                        }))
                                        return
                                await websocket.send_text(json.dumps({
                                    "type": "done",
                                    "text": full_text,
                                    "ask": qid,
                                }))
                            except Exception as e:
                                logger.error("Error during WebSocket ask streaming: %s", e)
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "message": str(e),
                                    "ask": qid,
                                }))

                        asyncio.create_task(handle_ask_stream(prompt, ask_id))
                elif action in ("interrupt", "cancel"):
                    if pipeline:
                        if pipeline.tts:
                            pipeline.tts.cancel()
                        if pipeline.llm:
                            pipeline.llm.cancel()
                        if pipeline.reasoning:
                            pipeline.reasoning.cancel_active_plan()
                elif action == "emergency_stop":
                    security_context.trigger_emergency_stop(data.get("reason", "WebSocket command"))
                elif action == "clear_emergency_stop":
                    security_context.clear_emergency_stop(data.get("reason", "WebSocket command"))
                elif action == "tts_cancel":
                    if pipeline and pipeline.tts:
                        pipeline.tts.cancel()
                elif action == "tts_speak":
                    text = data.get("text", "")
                    if text and pipeline and pipeline.tts and not security_context.is_emergency_stopped:
                        pipeline.tts.on_llm_start()
                        pipeline.tts.feed_text_delta(text)
                        pipeline.tts.flush_text()
                elif action == "reasoning_execute":
                    goal = data.get("goal")
                    if goal and pipeline and pipeline.reasoning and not security_context.is_emergency_stopped:
                        asyncio.create_task(pipeline.reasoning.execute_task(goal))
                elif action == "reasoning_cancel":
                    if pipeline and pipeline.reasoning:
                        pipeline.reasoning.cancel_active_plan()
                elif action == "computer_action":
                    catype = data.get("action_type") or data.get("subaction", "")
                    target = data.get("target", "")
                    args = data.get("args", {})
                    if catype and not security_context.is_emergency_stopped:
                        gateway_args = dict(args)
                        if target:
                            gateway_args["target"] = target
                        res = tool_gateway.execute_allowed(catype, gateway_args)
                        await websocket.send_text(json.dumps({
                            "type": "computer_action_result",
                            "action": catype,
                            "target": target,
                            "result": res,
                        }))
                elif action == "proactive_event":
                    ev_type = data.get("event_type")
                    if ev_type and pipeline and pipeline.proactive:
                        sev_str = data.get("severity", "low")
                        try:
                            sev = EventSeverity(sev_str.lower())
                        except Exception:
                            sev = EventSeverity.LOW
                        ev = ProactiveEvent(
                            event_type=ev_type,
                            source=data.get("source", "websocket"),
                            severity=sev,
                            data=data.get("data", {}),
                        )
                        pipeline.proactive.emit_event(ev)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket connection error: %s", e)
        manager.disconnect(websocket)


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Utility launcher to run with uvicorn."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()

