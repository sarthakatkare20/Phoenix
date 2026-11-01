"""
Text Chunker for Low-Latency Streaming TTS.
Intelligently buffers incoming LLM token deltas and splits at natural sentence & phrase boundaries.
"""

import re
from typing import List, Optional


class TextChunker:
    """
    Buffers streaming token deltas and emits coherent sentence/phrase chunks
    for low-latency speech synthesis.
    """

    def __init__(
        self,
        min_chars: int = 20,
        max_chars: int = 140,
    ):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buffer = ""

    @property
    def buffer(self) -> str:
        return self._buffer

    def reset(self) -> None:
        """Clear the internal text buffer."""
        self._buffer = ""

    def feed(self, delta: str) -> List[str]:
        """
        Feed a text delta from the LLM stream.
        Returns a list of completed phrase/sentence chunks ready for TTS.
        """
        if not delta:
            return []

        self._buffer += delta
        chunks: List[str] = []

        while self._buffer:
            # 1. Check for terminal punctuation (. ! ? or newline) within max_chars
            match_term = re.search(r"([.!?\n]+)\s*", self._buffer)
            if match_term and match_term.end() <= self.max_chars:
                end_pos = match_term.end()
                candidate = self._buffer[:end_pos].strip()
                if len(candidate) > 0:
                    # Ignore common abbreviations like 'Dr.', 'Mr.', 'e.g.' if too short
                    if candidate in ("Dr.", "Mr.", "Ms.", "e.g.", "i.e.") and len(self._buffer) > end_pos:
                        pass
                    else:
                        chunks.append(candidate)
                        self._buffer = self._buffer[end_pos:]
                        continue

            # 2. Check for soft clause boundaries (, ; :) if buffer is long enough
            if len(self._buffer) >= self.min_chars:
                match_soft = re.search(r"([,;:\u2014]+)\s+", self._buffer)
                if match_soft:
                    end_pos = match_soft.end()
                    candidate = self._buffer[:end_pos].strip()
                    if len(candidate) >= self.min_chars:
                        chunks.append(candidate)
                        self._buffer = self._buffer[end_pos:]
                        continue

            # 3. Check for max character safety threshold (break at last space)
            if len(self._buffer) >= self.max_chars:
                last_space = self._buffer.rfind(" ", 0, self.max_chars)
                if last_space > self.min_chars:
                    candidate = self._buffer[:last_space].strip()
                    chunks.append(candidate)
                    self._buffer = self._buffer[last_space:].lstrip()
                    continue
                else:
                    # Force split if no space found
                    candidate = self._buffer[:self.max_chars].strip()
                    chunks.append(candidate)
                    self._buffer = self._buffer[self.max_chars:].lstrip()
                    continue

            # No split boundary reached yet
            break

        return chunks

    def flush(self) -> Optional[str]:
        """
        Flush remaining text in buffer (called when LLM generation completes).
        """
        text = self._buffer.strip()
        self._buffer = ""
        return text if len(text) > 0 else None
