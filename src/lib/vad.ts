import { getMic } from './audio'

/**
 * Voice-activity detection and segment capture.
 *
 * This is the piece that makes the assistant reliable, and it exists because
 * the browser's SpeechRecognition does not. That API dies silently under
 * always-on use — Chrome throttles it, it stops firing events, and nothing you
 * can catch tells you it has gone deaf. Detecting that a human is speaking is
 * not a language problem, though; it is an energy problem, and energy on the
 * microphone signal is something we can measure ourselves, every frame, with no
 * black box that can quietly stop answering.
 *
 * So: a running-mean noise floor, a threshold above it, and a hysteresis gate.
 * When the signal crosses the threshold a fresh recorder starts; when it falls
 * quiet for long enough the recorder stops and hands back one self-contained
 * audio blob for the bridge to transcribe. The detection is instant and local
 * — that is what makes barge-in feel natural — and the words come back a moment
 * later from a real transcriber that cannot silently fail the way the browser
 * one did.
 *
 * Hearing himself is the one hard part. The microphone picks up JARVIS's own
 * voice through the speakers, and raw energy cannot tell that from the user.
 * Two things handle it: getUserMedia is asked for echo cancellation, which
 * removes most of the playback, and while he is speaking the trigger threshold
 * is raised so the residue that leaks through does not cross it. A text check
 * after transcription is the final backstop, in voice.ts.
 */

export type VadHandlers = {
  /** The signal crossed into speech. Instant; this is the barge-in trigger. */
  onStart: () => void
  /** Speech ended. The blob is one complete, decodable audio file. */
  onEnd: (audio: Blob, ms: number) => void
  /** 0..1 smoothed input level, for the caption/orb while capturing. */
  onLevel: (v: number) => void
  /** Sharp acoustic impulse (hand clap / snap) detected. */
  onClap?: () => void
  /** Capture is impossible — no microphone, or no MediaRecorder support. */
  onError: (message: string) => void
}

export type Vad = {
  stop: () => void
  /** Raise the trigger bar while JARVIS speaks, so his own playback leaking
   *  past echo cancellation does not register as the user talking. */
  setGuard: (on: boolean) => void
  live: () => boolean
  /** Live internals, for the diagnostics panel. */
  meter: () => { energy: number; floor: number; threshold: number; speaking: boolean }
}

// ---------------------------------------------------------------------------
// Tuning
// ---------------------------------------------------------------------------

/** How far above the noise floor the signal must rise to count as speech.
 *  The floor tracks the room, so this is a ratio, not an absolute level. */
const TRIGGER_OVER_FLOOR = 2.5
/** While he is speaking, demand this much more, so residual echo is ignored. */
const GUARD_BOOST = 6.0
/** Falling back below trigger×this ends the segment. Hysteresis stops a single
 *  dip mid-word from cutting a sentence in half. */
const RELEASE_RATIO = 0.6

/** Sustained energy for this long confirms speech rather than a knock or click. */
const START_MS = 110
/**
 * Quiet for this long ends the SEGMENT — which is no longer the same thing as
 * ending the turn.
 *
 * It used to be both, which is why this number was impossible to set: long
 * enough not to clip someone thinking mid-sentence meant every completed
 * question also sat waiting for nothing. Deciding whether the thought is
 * actually finished now happens a layer up, on the words rather than the
 * energy (see makeAssembler in voice.ts), so this can go back to being what it
 * should always have been — a cheap "have they stopped making noise" — and the
 * shorter window gets the transcript moving sooner.
 */
const SILENCE_MS = 650
/** Nobody speaks one segment for this long; cut it and transcribe what we have. */
const MAX_MS = 20000

/** The floor adapts slowly upward (a fan spinning up) and quickly downward (a
 *  door closing), so it settles to genuine ambient noise without chasing speech. */
const FLOOR_UP = 0.004
const FLOOR_DOWN = 0.03

function pickMime(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ]
  for (const m of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(m)) {
      return m
    }
  }
  return ''
}

export async function startVad(h: VadHandlers): Promise<Vad> {
  let stream: MediaStream
  try {
    stream = await getMic()
  } catch (err) {
    h.onError(
      err instanceof DOMException && err.name === 'NotAllowedError'
        ? 'Microphone access denied — voice input is unavailable.'
        : 'No microphone available.',
    )
    return { stop: () => {}, setGuard: () => {}, live: () => false, meter: () => ({ energy: 0, floor: 0, threshold: 0, speaking: false }) }
  }

  if (typeof MediaRecorder === 'undefined') {
    h.onError('This browser cannot record audio — voice input is unavailable.')
    return { stop: () => {}, setGuard: () => {}, live: () => false, meter: () => ({ energy: 0, floor: 0, threshold: 0, speaking: false }) }
  }

  const mime = pickMime()
  const ctx = new AudioContext()
  void ctx.resume()

  // Keep AudioContext alive across tab switches and window minimize
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', () => {
      if (ctx.state === 'suspended') void ctx.resume()
    })
  }

  const source = ctx.createMediaStreamSource(stream)
  // 220Hz High-pass filter cuts off ceiling fan, table fan drone & ambient rumble
  const filter = ctx.createBiquadFilter()
  filter.type = 'highpass'
  filter.frequency.value = 220
  filter.Q.value = 0.7

  const analyser = ctx.createAnalyser()
  analyser.fftSize = 1024
  analyser.smoothingTimeConstant = 0.35
  source.connect(filter)
  filter.connect(analyser)

  // Web Audio processor node runs on real-time audio thread and NEVER pauses in background
  let processor: ScriptProcessorNode | null = null
  try {
    processor = ctx.createScriptProcessor(2048, 1, 1)
    const muteGain = ctx.createGain()
    muteGain.gain.value = 0
    filter.connect(processor)
    processor.connect(muteGain)
    muteGain.connect(ctx.destination)
  } catch {
    /* fallback to raf/timer */
  }

  const buf = new Float32Array(analyser.fftSize)

  let stopped = false
  let guard = false
  let floor = 0.01
  let smoothEnergy = 0
  let threshold = 0

  // Segment state.
  let recorder: MediaRecorder | null = null
  let parts: Blob[] = []
  let armedAt = 0 // energy first rose; recording may be pre-rolling
  let speaking = false
  let speechStartedAt = 0
  let lastLoud = 0
  let lastClap = 0
  let raf = 0

  const rms = (): number => {
    analyser.getFloatTimeDomainData(buf)
    let sum = 0
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
    return Math.sqrt(sum / buf.length)
  }

  const startRecorder = () => {
    parts = []
    try {
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
    } catch {
      recorder = new MediaRecorder(stream)
    }
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size) parts.push(e.data)
    }
    recorder.start()
  }

  const discardRecorder = () => {
    if (!recorder) return
    try {
      recorder.ondataavailable = null
      if (recorder.state !== 'inactive') recorder.stop()
    } catch {
      /* already gone */
    }
    recorder = null
    parts = []
  }

  const endSegment = () => {
    const rec = recorder
    const startedAt = speechStartedAt
    speaking = false
    speechStartedAt = 0
    if (!rec) return
    recorder = null

    const finalise = () => {
      const type = rec.mimeType || mime || 'audio/webm'
      const blob = new Blob(parts, { type })
      parts = []
      const ms = startedAt ? performance.now() - startedAt : 0
      h.onEnd(blob, ms)
    }
    rec.onstop = finalise
    try {
      if (rec.state !== 'inactive') rec.stop()
      else finalise()
    } catch {
      finalise()
    }
  }

  const tick = () => {
    if (stopped) return

    const energy = rms()
    const now = performance.now()

    // Detect sudden hand clap impulse (sharp energy rise from baseline)
    if (!guard && h.onClap && now - lastClap > 1000) {
      const spike = energy - smoothEnergy
      if (energy > 0.14 && spike > 0.08 && energy > floor * 4.5) {
        lastClap = now
        h.onClap()
      }
    }

    smoothEnergy += (energy - smoothEnergy) * 0.5
    h.onLevel(Math.min(1, smoothEnergy * 12))

    // Adapt the floor only when we are confident this is not speech, and not during playback.
    if (!speaking && armedAt === 0 && !guard) {
      const rate = smoothEnergy > floor ? FLOOR_UP : FLOOR_DOWN
      floor += (smoothEnergy - floor) * rate
      floor = Math.max(0.003, Math.min(floor, 0.08))
    }

    const minGate = guard ? 0.045 : 0.018
    threshold = Math.max(minGate, floor * TRIGGER_OVER_FLOOR * (guard ? GUARD_BOOST : 1))
    const release = threshold * RELEASE_RATIO

    if (!speaking) {
      if (smoothEnergy > threshold) {
        if (armedAt === 0) {
          armedAt = now
          startRecorder()
        } else if (now - armedAt >= (guard ? 280 : START_MS)) {
          speaking = true
          speechStartedAt = armedAt
          lastLoud = now
          h.onStart()
        }
      } else if (armedAt !== 0) {
        armedAt = 0
        discardRecorder()
      }
    } else {
      if (smoothEnergy > release) lastLoud = now
      const quietFor = now - lastLoud
      const runFor = now - speechStartedAt
      if (quietFor >= SILENCE_MS || runFor >= MAX_MS) {
        armedAt = 0
        endSegment()
      }
    }
  }

  if (processor) {
    processor.onaudioprocess = (e) => {
      const out = e.outputBuffer.getChannelData(0)
      out.fill(0)
      if (!stopped) tick()
    }
  }

  // Also run RAF loop when visible for high framerate visualisations
  const loop = () => {
    if (stopped) return
    raf = requestAnimationFrame(loop)
    if (!processor) tick()
  }
  loop()

  return {
    stop: () => {
      stopped = true
      cancelAnimationFrame(raf)
      if (processor) {
        processor.onaudioprocess = null
        try {
          processor.disconnect()
        } catch {}
      }
      discardRecorder()
      try {
        source.disconnect()
        void ctx.close()
      } catch {
        /* noop */
      }
    },
    setGuard: (on) => {
      if (guard && !on) {
        // Just stopped speaking — drop floor back down immediately so user's follow-up is heard
        floor = Math.min(floor, 0.012)
      }
      guard = on
    },
    live: () => !stopped,
    meter: () => ({ energy: smoothEnergy, floor, threshold, speaking }),
  }
}
