/**
 * Sarvam Saaras V4 Speech-to-Text Client for Project Phoenix.
 * Bridges browser audio capture to Python FastAPI `/api/stt/sarvam`.
 * Provides deep phonetic comprehension for Indian English, Hindi, and code-mixed Hinglish.
 */

export async function transcribeWithSarvam(audioBlob: Blob): Promise<string | null> {
  try {
    const formData = new FormData()
    formData.append('file', audioBlob, 'utterance.wav')

    const res = await fetch('http://127.0.0.1:8000/api/stt/sarvam', {
      method: 'POST',
      body: formData,
    })

    if (res.ok) {
      const data = await res.json()
      if (data.transcript && data.transcript.trim()) {
        return data.transcript.trim()
      }
    } else {
      const err = await res.json().catch(() => ({}))
      console.warn('[Sarvam] Backend response:', err)
    }
  } catch (e) {
    console.warn('[Sarvam] Failed to reach Sarvam endpoint:', e)
  }
  return null
}
