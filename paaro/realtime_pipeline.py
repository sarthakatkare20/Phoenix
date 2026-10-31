"""
Realtime Voice Pipeline Coordinator.
Connects Audio Capture -> Silero VAD -> Speech State Machine -> Security Layer -> WebSocket Event Dispatcher.
"""

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import numpy as np

from .config import PaaroSettings, settings
from .security import SecurityContext, security_context
from .silero_vad import SileroVAD
from .speech_state_machine import SpeechState, SpeechStateMachine
from .audio_capture import AudioCaptureStream
from .streaming_stt import StreamingSTT
from .streaming_llm import StreamingLLM
from .kokoro_tts import StreamingTTS
from .memory.service import MemoryService
from .memory.context import ContextBuilder
from .reasoning import ReasoningEngine
from .proactive import (
    EventBus,
    EventEvaluator,
    EventSeverity,
    ProactiveBrain,
    ProactiveEngine,
    ProactiveEventQueue,
    UserActivityState,
)

logger = logging.getLogger("paaro.pipeline")


class RealtimeVoicePipeline:
    """
    Main Realtime Voice, VAD, Streaming STT, Streaming LLM, Streaming TTS, Memory, Reasoning, and Proactive Orchestrator.
    """

    def __init__(
        self,
        config: Optional[PaaroSettings] = None,
        security: Optional[SecurityContext] = None,
        stt: Optional[StreamingSTT] = None,
        llm: Optional[StreamingLLM] = None,
        tts: Optional[StreamingTTS] = None,
        memory_service: Optional[MemoryService] = None,
        proactive_engine: Optional[ProactiveEngine] = None,
        reasoning_engine: Optional[ReasoningEngine] = None,
    ):
        self.config = config or settings
        self.security = security or security_context
        self._async_loop: Optional[Any] = None

        # Memory Service
        if memory_service is not None:
            self.memory_service: Optional[MemoryService] = memory_service
        elif self.config.MEMORY_ENABLED:
            self.memory_service = MemoryService(default_user_id=self.config.DEFAULT_USER_ID)
        else:
            self.memory_service = None

        self.active_session_id: str = (
            self.memory_service.get_or_create_active_session().id
            if self.memory_service
            else ""
        )

        # Components
        self.vad = SileroVAD(
            threshold=self.config.VAD_THRESHOLD,
            sample_rate=self.config.AUDIO_SAMPLE_RATE,
        )
        self.state_machine = SpeechStateMachine(
            speech_start_confirmation=self.config.VAD_SPEECH_START_CONFIRMATION,
            silence_duration_sec=self.config.VAD_SILENCE_DURATION,
            frame_duration_sec=self.config.AUDIO_FRAME_MS / 1000.0,
        )

        # Streaming STT (faster-whisper)
        if stt is not None:
            self.stt: Optional[StreamingSTT] = stt
        elif self.config.STT_ENABLED:
            self.stt = StreamingSTT(config=self.config)
        else:
            self.stt = None

        if self.stt:
            self.stt.add_listener(self._on_stt_event)

        # Streaming LLM (Ollama)
        if llm is not None:
            self.llm: Optional[StreamingLLM] = llm
        elif self.config.LLM_ENABLED:
            self.llm = StreamingLLM(
                config=self.config,
                security=self.security,
                memory_service=self.memory_service,
            )
        else:
            self.llm = None

        if self.llm:
            self.llm.add_listener(self._broadcast_event)

        # Streaming TTS (Kokoro / Local)
        if tts is not None:
            self.tts: Optional[StreamingTTS] = tts
        elif self.config.TTS_ENABLED:
            self.tts = StreamingTTS(config=self.config)
        else:
            self.tts = None

        if self.tts:
            self.tts.add_listener(self._broadcast_event)

        # Proactive Engine (Step 7)
        if proactive_engine is not None:
            self.proactive: Optional[ProactiveEngine] = proactive_engine
        elif self.config.PROACTIVE_ENABLED:
            bus = EventBus()
            evaluator = EventEvaluator(
                min_severity=EventSeverity.LOW,
                default_cooldown_sec=self.config.PROACTIVE_DEFAULT_COOLDOWN_SEC,
            )
            brain = ProactiveBrain(
                evaluator=evaluator,
                llm=self.llm,
                tts=self.tts,
                security=self.security,
                memory_service=self.memory_service,
                auto_speech=self.config.PROACTIVE_AUTO_SPEECH,
            )
            self.proactive = ProactiveEngine(
                config=self.config,
                event_bus=bus,
                evaluator=evaluator,
                brain=brain,
                queue=ProactiveEventQueue(max_size=self.config.PROACTIVE_QUEUE_SIZE),
                user_state_provider=self.get_user_activity_state,
            )
        else:
            self.proactive = None

        if self.proactive:
            self.proactive.brain.add_listener(self._broadcast_event)

        # Reasoning Engine (Step 8)
        if reasoning_engine is not None:
            self.reasoning: Optional[ReasoningEngine] = reasoning_engine
        elif self.config.REASONING_ENABLED:
            self.reasoning = ReasoningEngine(
                config=self.config,
                llm=self.llm,
                tts=self.tts,
                security=self.security,
                memory_service=self.memory_service,
            )
        else:
            self.reasoning = None

        if self.reasoning:
            self.reasoning.add_listener(self._broadcast_event)

        # Computer Control Subsystem (Step 9)
        if self.config.COMPUTER_CONTROL_ENABLED:
            try:
                from .computer import computer_controller
                self.computer = computer_controller
                self.computer.add_listener(self._broadcast_event)
            except Exception as e:
                logger.warning("Could not initialize computer controller in pipeline: %s", e)
                self.computer = None
        else:
            self.computer = None

        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)
        self.audio_capture = AudioCaptureStream(
            sample_rate=self.config.AUDIO_SAMPLE_RATE,
            channels=self.config.AUDIO_CHANNELS,
            frame_samples=self.config.AUDIO_FRAME_SAMPLES,
            device_index=self.config.AUDIO_DEVICE_INDEX,
            callback=self._on_raw_audio_chunk,
        )

        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._event_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._lock = threading.Lock()

        # Connect state machine notifications
        self.state_machine.add_listener(self._on_state_machine_event)

        # Connect emergency stop notifications
        self.security.add_emergency_listener(self._on_emergency_stop_change)

        # Barge-in state and metrics
        self._barge_in_count = 0
        self._false_barge_in_count = 0
        self._last_barge_in_to_audio_stop_ms = 0.0
        self._tts_playback_start_time: Optional[float] = None

        # Listen for TTS playback start/end to track playback window
        if self.tts:
            self.tts.add_listener(self._on_tts_lifecycle_event)

    def _on_tts_lifecycle_event(self, event: Dict[str, Any]) -> None:
        ev_type = event.get("type")
        if ev_type == "tts_audio_start":
            self._tts_playback_start_time = time.time()
        elif ev_type in ("tts_done", "tts_cancelled"):
            self._tts_playback_start_time = None

    def get_user_activity_state(self) -> UserActivityState:
        """Derive current interaction state for proactive evaluation."""
        if self.security.is_emergency_stopped:
            return UserActivityState.BUSY
        if self.reasoning and self.reasoning.is_executing_plan:
            return UserActivityState.THINKING
        if self.state_machine.current_state in (SpeechState.SPEECH_START, SpeechState.SPEAKING):
            return UserActivityState.LISTENING
        if self.llm and self.llm._is_generating:
            return UserActivityState.THINKING
        if self.tts and self.tts.is_speaking:
            return UserActivityState.SPEAKING
        return UserActivityState.IDLE

    @property
    def is_assistant_speaking(self) -> bool:
        """Returns True if the assistant is currently speaking or generating speech."""
        return bool(
            (self.tts and self.tts.is_speaking)
            or (self.llm and self.llm._is_generating)
            or (self.reasoning and self.reasoning.is_executing_plan)
        )

    def get_barge_in_metrics(self) -> Dict[str, Any]:
        return {
            "barge_in_enabled": self.config.BARGE_IN_ENABLED,
            "barge_in_count": self._barge_in_count,
            "false_barge_in_count": self._false_barge_in_count,
            "last_barge_in_to_audio_stop_ms": round(self._last_barge_in_to_audio_stop_ms, 2),
            "tts_metrics": self.tts.get_metrics() if self.tts else {},
        }

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def current_state(self) -> SpeechState:
        return self.state_machine.current_state

    def set_async_loop(self, loop: Any) -> None:
        self._async_loop = loop
        if self.proactive:
            self.proactive.set_async_loop(loop)
            self.proactive.start(loop)

    def add_event_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        """Add listener for VAD, STT, LLM and Barge-in events."""
        with self._lock:
            if listener not in self._event_listeners:
                self._event_listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

    def _broadcast_event(self, event: Dict[str, Any]) -> None:
        listeners = []
        with self._lock:
            listeners = list(self._event_listeners)

        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error("Error dispatching event to listener: %s", e)

    def _on_stt_event(self, event: Dict[str, Any]) -> None:
        self._broadcast_event(event)

        # On final STT transcript, automatically trigger streaming LLM or reasoning if enabled
        if event.get("type") == "stt" and event.get("status") == "final":
            text = event.get("text", "").strip()
            if text and not self.security.is_emergency_stopped:
                if self._async_loop and self._async_loop.is_running():
                    import asyncio
                    asyncio.run_coroutine_threadsafe(self._process_llm_stream(text), self._async_loop)

    async def _process_llm_stream(self, prompt: str) -> None:
        if self.security.is_emergency_stopped:
            return

        # Step 8: Multi-step Reasoning & Planning Fast Path check
        if self.reasoning:
            try:
                handled = await self.reasoning.handle_request(prompt, session_id=self.active_session_id)
                if handled:
                    return
            except Exception as e:
                logger.error("Error evaluating reasoning handle_request: %s", e)

        # Direct & Simple requests use the fast path streaming LLM
        if self.llm and not self.security.is_emergency_stopped:
            try:
                import inspect
                try:
                    sig = inspect.signature(self.llm.stream_response)
                    accepts_session_id = "session_id" in sig.parameters or any(
                        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                    )
                except Exception:
                    accepts_session_id = True

                if accepts_session_id:
                    stream = self.llm.stream_response(prompt, session_id=self.active_session_id)
                else:
                    stream = self.llm.stream_response(prompt)

                async for event in stream:
                    if isinstance(event, str):
                        if self.tts:
                            self.tts.feed_text_delta(event)
                        continue

                    status = event.get("status")
                    gen_id = event.get("generation_id")
                    if status == "start":
                        if self.tts:
                            self.tts.on_llm_start(generation_id=gen_id)
                    elif status == "delta":
                        delta = event.get("text", "")
                        if self.tts and delta:
                            self.tts.feed_text_delta(delta, generation_id=gen_id)
                    elif status == "done":
                        if self.tts:
                            self.tts.flush_text(generation_id=gen_id)
                if self.tts:
                    self.tts.flush_text()
            except Exception as e:
                logger.error("Error in LLM background stream: %s", e)

    def _on_state_machine_event(self, state: SpeechState, timestamp: float, metadata: dict) -> None:
        # Check for Barge-in Interruption (User starts speaking while Assistant is active)
        if state == SpeechState.SPEECH_START and self.is_assistant_speaking:
            t_barge_start = time.time()
            logger.info("Barge-in detected: User interrupted Paaro while speaking.")
            
            active_tts_gen = self.tts.active_generation_id if self.tts else ""

            # Immediately cancel TTS and stop playback
            tts_stop_ms = 0.0
            if self.tts:
                tts_stop_ms = self.tts.cancel()

            # Immediately cancel active LLM generation
            cancelled_llm_gen = ""
            if self.llm:
                cancelled_llm_gen = self.llm.cancel()

            # Cancel active reasoning plan if running
            if self.reasoning:
                self.reasoning.cancel_active_plan()

            cancelled_gen_id = cancelled_llm_gen or active_tts_gen
            t_barge_end = time.time()
            total_barge_latency_ms = (t_barge_end - t_barge_start) * 1000.0

            self._barge_in_count += 1
            self._last_barge_in_to_audio_stop_ms = total_barge_latency_ms

            # Broadcast barge-in lifecycle events
            self._broadcast_event({
                "type": "barge_in_detected",
                "barge_in_to_audio_stop_ms": round(total_barge_latency_ms, 2),
                "tts_stop_ms": round(tts_stop_ms, 2),
                "cancelled_generation_id": cancelled_gen_id,
                "timestamp": int(t_barge_start * 1000),
            })
            if cancelled_gen_id:
                self._broadcast_event({
                    "type": "generation_invalidated",
                    "generation_id": cancelled_gen_id,
                    "timestamp": int(time.time() * 1000),
                })

        event = {
            "type": "vad",
            "state": state.value,
            "timestamp": int(timestamp * 1000),
            **metadata,
        }
        self._broadcast_event(event)

        # Notify Streaming STT
        if self.stt:
            if state == SpeechState.SPEECH_START:
                self.stt.on_speech_start(timestamp)
            elif state == SpeechState.SPEECH_END:
                self.stt.on_speech_end(timestamp)

    def _on_emergency_stop_change(self, stopped: bool) -> None:
        if stopped:
            logger.warning("Emergency stop triggered: resetting speech state and halting VAD/STT/LLM/TTS/Reasoning processing.")
            self.state_machine.reset()
            self.vad.reset_state()
            if self.stt:
                self.stt.cancel()
            if self.llm:
                self.llm.cancel()
            if self.tts:
                self.tts.cancel()
            if self.reasoning:
                self.reasoning.cancel_active_plan()
            self._broadcast_event({
                "type": "security",
                "state": "emergency_stopped",
                "timestamp": int(time.time() * 1000),
                "reason": self.security.halt_reason,
            })
        else:
            logger.info("Emergency stop cleared: resuming speech state machine.")
            self._broadcast_event({
                "type": "security",
                "state": "emergency_cleared",
                "timestamp": int(time.time() * 1000),
            })

    def _on_raw_audio_chunk(self, chunk: np.ndarray) -> None:
        if not self._is_running or self.security.is_emergency_stopped:
            return

        try:
            self._audio_queue.put_nowait(chunk)
        except queue.Full:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                pass
            self._audio_queue.put_nowait(chunk)

    def _worker_loop(self) -> None:
        """Background thread worker pulling audio frames, running Silero VAD and feeding STT."""
        logger.info("RealtimeVoicePipeline VAD worker thread started.")
        
        while self._is_running:
            if self.security.is_emergency_stopped:
                time.sleep(0.05)
                continue

            try:
                frame = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if frame is None or not self._is_running:
                break

            try:
                # Process Silero VAD
                is_speech, prob = self.vad.is_speech(frame)

                # Echo / Self-Speech Protection during TTS Playback
                confirmation_frames = self.config.VAD_SPEECH_START_CONFIRMATION
                if self.is_assistant_speaking:
                    if not self.config.BARGE_IN_ENABLED:
                        # Echo suppression: ignore mic audio completely while assistant speaks
                        is_speech = False
                    else:
                        now = time.time()
                        # 1. Grace Period check (ignore initial playback transient)
                        if (
                            self._tts_playback_start_time is not None
                            and (now - self._tts_playback_start_time) < (self.config.BARGE_IN_GRACE_PERIOD_MS / 1000.0)
                        ):
                            is_speech = False
                        else:
                            # 2. RMS Energy calculation
                            frame_rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
                            # 3. Guard threshold and minimum energy
                            if prob < self.config.BARGE_IN_THRESHOLD or frame_rms < self.config.BARGE_IN_MIN_ENERGY:
                                if is_speech:
                                    self._false_barge_in_count += 1
                                is_speech = False

                        # Require elevated confirmation frames during speaking
                        confirmation_frames = self.config.BARGE_IN_CONFIRMATION_FRAMES

                # Feed into State Machine
                self.state_machine.update(is_speech, prob, speech_start_confirmation=confirmation_frames)

                # Feed audio chunk into Streaming STT if speaking
                if self.stt and self.state_machine.current_state in (SpeechState.SPEAKING, SpeechState.SPEECH_START):
                    self.stt.feed_audio(frame)

            except Exception as e:
                logger.error("VAD/STT worker error: %s", e)

        logger.info("RealtimeVoicePipeline VAD worker thread ended.")

    def start(self) -> None:
        """Start continuous audio capture and VAD/STT processing."""
        with self._lock:
            if self._is_running:
                return

            self._is_running = True
            self.vad.reset_state()
            self.state_machine.reset()
            if self.stt:
                self.stt.cancel()

            # Start worker thread
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="PaaroVadWorker",
                daemon=True,
            )
            self._worker_thread.start()

            # Start audio capture
            self.audio_capture.start()
            logger.info("RealtimeVoicePipeline successfully started.")

    def stop(self) -> None:
        """Stop audio capture and VAD/STT processing."""
        with self._lock:
            if not self._is_running:
                return

            self._is_running = False

            # Stop capture
            self.audio_capture.stop()

            # Signal worker thread
            try:
                self._audio_queue.put_nowait(None)
            except Exception:
                pass

            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=1.0)
            self._worker_thread = None

            self.state_machine.reset()
            self.vad.reset_state()
            if self.stt:
                self.stt.cancel()
                self.stt.close()
            if self.tts:
                self.tts.cancel()
                self.tts.close()
            if self.proactive:
                self.proactive.stop()
            logger.info("RealtimeVoicePipeline stopped.")

