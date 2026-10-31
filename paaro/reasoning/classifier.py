"""
Task Complexity Classifier for Paaro Reasoning Engine (Step 8).
Provides ultra-fast deterministic classification with optional LLM fallback.
"""

import json
import logging
import re
import time
from typing import Optional

from .models import TaskComplexity
from ..streaming_llm import StreamingLLM

logger = logging.getLogger("paaro.reasoning.classifier")


class TaskComplexityClassifier:
    """
    Classifies incoming user instructions into DIRECT, SIMPLE, MULTI_STEP, or COMPLEX.
    Guarantees < 0.1ms fast-path execution for direct single-turn requests.
    """

    def __init__(self, llm: Optional[StreamingLLM] = None):
        self.llm = llm

    def classify_deterministic(self, user_prompt: str) -> TaskComplexity:
        """
        Deterministic fast-path classification in < 0.1ms.
        """
        text = user_prompt.strip().lower()

        # 1. Deterministic COMPLEX patterns (diagnosis, fixing, multi-phase verification)
        complex_indicators = [
            r"fix\s+.*(?:test|bug|issue|error|server|code)",
            r"diagnose\s+.*(?:and|then|fix)",
            r"find\s+why\s+.*(?:fix|rerun|verify)",
            r"check\s+.*run\s+tests\s+.*fix",
            r"refactor\s+.*and\s+verify",
            r"troubleshoot\s+.*and\s+restart",
            r"debug\s+.*and\s+fix",
        ]
        for pattern in complex_indicators:
            if re.search(pattern, text):
                logger.info("[REASONING] Classified '%s' -> COMPLEX (deterministic pattern)", text[:40])
                return TaskComplexity.COMPLEX

        # 2. Deterministic MULTI_STEP patterns (inspect + run, sequence of dependent tools)
        multistep_indicators = [
            r"run\s+(?:the\s+|my\s+)?tests?\s+and\s+(?:tell|show|report|check)",
            r"check\s+.*(?:repo|project|codebase)\s+and\s+run\s+tests?",
            r"inspect\s+.*and\s+(?:check|analyze|list)",
            r"check\s+logs\s+and\s+(?:restart|verify)",
            r"build\s+.*and\s+run\s+tests?",
            r"first\s+.*then\s+.*(?:finally|next)",
            r"list\s+directory\s+and\s+.*",
            r"check\s+git\s+status\s+and\s+run\s+tests",
            r"restart\s+it\s+and\s+verify",
            r"open\s+.*(?:and|,)\s+.*(?:and|,)\s+.*",
        ]
        for pattern in multistep_indicators:
            if re.search(pattern, text):
                logger.info("[REASONING] Classified '%s' -> MULTI_STEP (deterministic pattern)", text[:40])
                return TaskComplexity.MULTI_STEP

        # 3. Deterministic SIMPLE patterns (1-2 predictable sequential actions)
        simple_indicators = [
            r"open\s+.*and\s+(?:open|search|go\s+to|check)",
            r"search\s+for\s+.*and\s+open",
            r"start\s+\w+\s+and\s+\w+",
            r"check\s+.*and\s+(?:open|start|check)",
            r"launch\s+.*and\s+check",
        ]
        for pattern in simple_indicators:
            if re.search(pattern, text):
                logger.info("[REASONING] Classified '%s' -> SIMPLE (deterministic pattern)", text[:40])
                return TaskComplexity.SIMPLE

        # 4. Deterministic DIRECT patterns (Immediate single questions or single tools)
        direct_indicators = [
            r"^(?:what|who|when|where|why|how)\s+.*",
            r"^(?:is|are)\s+.*(?:running|active|alive|started|open)\??$",
            r"^(?:what(?:'s|\s+is)\s+running(?:\s+right\s+now)?|what\s+processes\s+are\s+running)\??$",
            r"^(?:open|launch|start|close|kill|stop|focus)\s+.*",
            r"^(?:play|pause|stop|resume|next|prev|volume)\s*.*",
            r"^(?:remember|forget|show|list)\s+.*",
            r"^(?:hi|hello|hey|good\s+morning|good\s+evening|jarvis|paaro|hello\s+there)[\.!\?]?$",
            r"^(?:tell\s+me|calculate|what's\s+the\s+weather|what's\s+my\s+cpu|time|date).*",
            r"^(?:cpu|ram|memory|disk|system\s+stats|system\s+state).*",
        ]
        for pattern in direct_indicators:
            if re.search(pattern, text):
                logger.debug("[REASONING] Classified '%s' -> DIRECT (fast path)", text[:40])
                return TaskComplexity.DIRECT

        # If sentence contains multiple action verbs joined by "and then", "then", or commas
        if re.search(r"\b(?:then|and\s+then|after\s+that)\b", text):
            logger.info("[REASONING] Classified '%s' -> MULTI_STEP (conjunctions)", text[:40])
            return TaskComplexity.MULTI_STEP

        # Default fallback for standard conversational queries is DIRECT (fast path)
        return TaskComplexity.DIRECT

    async def classify(self, user_prompt: str) -> TaskComplexity:
        """
        Classify user request complexity.
        Uses deterministic fast path; if ambiguous and LLM is present, uses LLM classification.
        """
        deterministic = self.classify_deterministic(user_prompt)
        if deterministic != TaskComplexity.DIRECT or not self.llm:
            return deterministic
        return await self.classify_with_llm(user_prompt)

    async def classify_with_llm(self, user_prompt: str) -> TaskComplexity:
        """
        Optional LLM-assisted classification for ambiguous prompts.
        """
        fast_res = self.classify_deterministic(user_prompt)
        if not self.llm:
            return fast_res

        prompt = (
            f"Classify the following user task into exactly one category: "
            "DIRECT (single immediate response or tool), "
            "SIMPLE (1-2 quick actions), "
            "MULTI_STEP (sequence of 3+ dependent steps), or "
            "COMPLEX (requires diagnosis, coding, fixing, or replanning).\n\n"
            f"Task: \"{user_prompt}\"\n\n"
            "Respond with only the category name in uppercase (e.g. MULTI_STEP)."
        )
        try:
            full_text = ""
            if hasattr(self.llm, "generate") and callable(getattr(self.llm, "generate")):
                res = await self.llm.generate(prompt)
                full_text = str(res)
            elif hasattr(self.llm, "stream_response"):
                async for delta in self.llm.stream_response(prompt):
                    if isinstance(delta, dict) and delta.get("status") == "delta":
                        full_text += delta.get("text", "")
                    elif isinstance(delta, str):
                        full_text += delta

            clean = full_text.strip().upper()
            if "COMPLEX" in clean:
                return TaskComplexity.COMPLEX
            if "MULTI_STEP" in clean or "MULTISTEP" in clean:
                return TaskComplexity.MULTI_STEP
            if "SIMPLE" in clean:
                return TaskComplexity.SIMPLE
            if "DIRECT" in clean:
                return TaskComplexity.DIRECT
        except Exception as e:
            logger.error("LLM classification error: %s", e)

        return fast_res
