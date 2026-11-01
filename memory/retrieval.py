"""
Relevance Scoring and Retrieval Engine for Paaro Memories (Step 6).
Deterministic ranking based on keyword overlap, category weights, importance, and recency.
"""

import math
import re
import time
from typing import List, Optional, Tuple

from memory.models import Memory, MemoryCategory

# Category priority multipliers
CATEGORY_WEIGHTS = {
    MemoryCategory.PROFILE: 1.3,
    MemoryCategory.PREFERENCE: 1.25,
    MemoryCategory.PROJECT: 1.15,
    MemoryCategory.FACT: 1.0,
    MemoryCategory.ROUTINE: 0.9,
    MemoryCategory.TASK: 0.85,
    MemoryCategory.CONTEXT: 0.75,
}

# Stop words to ignore during token overlap scoring
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "and", "or", "in", "on", "at", 
    "to", "for", "of", "with", "by", "from", "about", "what", "how", "why", "when",
    "who", "i", "me", "my", "you", "your", "it", "its", "that", "this", "do", "did",
    "can", "will", "would", "should", "could", "please", "hey", "jarvis", "paaro",
}


class MemoryRetriever:
    """
    Ranks stored memories against a query using term overlap, importance, and recency.
    """

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        words = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
        return {w for w in words if w not in STOP_WORDS and len(w) > 1}

    @classmethod
    def score_memory(
        cls,
        memory: Memory,
        query_tokens: set[str],
        now: Optional[float] = None,
    ) -> float:
        """
        Calculate a composite relevance score for a memory item (0.0 to 10.0+).
        """
        now = now or time.time()
        mem_tokens = cls._tokenize(memory.content)

        if not mem_tokens:
            return 0.0

        # 1. Term Overlap Score (Jaccard / Token Overlap)
        overlap = query_tokens.intersection(mem_tokens)
        if not query_tokens:
            overlap_score = 0.0
        else:
            overlap_score = len(overlap) / max(1, math.sqrt(len(query_tokens) * len(mem_tokens)))

        # Direct Substring / Entity Match boost
        # E.g. if query contains "hinglish" and memory says "I prefer Hinglish"
        direct_match = any(t in memory.content.lower() for t in query_tokens if len(t) > 2)
        if direct_match:
            overlap_score += 0.5

        # 2. Category Multiplier
        cat_mult = CATEGORY_WEIGHTS.get(memory.category, 1.0)

        # 3. Importance & Confidence
        importance = max(0.1, min(1.0, memory.importance))
        confidence = max(0.1, min(1.0, memory.confidence))

        # 4. Recency Decay (half-life of 30 days = 2592000s)
        age_sec = max(0.0, now - memory.updated_at)
        recency = math.exp(-age_sec / (30 * 86400))  # 1.0 down to ~0.37 at 30 days

        # Base profile/preference baseline (always have slight passive relevance)
        baseline = 0.15 if memory.category in (MemoryCategory.PROFILE, MemoryCategory.PREFERENCE) else 0.0

        score = (overlap_score * 3.0 + baseline) * cat_mult * importance * confidence * (0.8 + 0.2 * recency)
        return score

    @classmethod
    def retrieve_relevant(
        cls,
        memories: List[Memory],
        query: str,
        top_k: int = 5,
        min_score: float = 0.15,
    ) -> List[Tuple[Memory, float]]:
        """
        Filter and rank memories by relevance score.
        Returns list of (Memory, score) tuples sorted descending by score.
        """
        if not memories:
            return []

        query_tokens = cls._tokenize(query)
        scored: List[Tuple[Memory, float]] = []

        now = time.time()
        for mem in memories:
            score = cls.score_memory(mem, query_tokens, now=now)
            if score >= min_score:
                scored.append((mem, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
