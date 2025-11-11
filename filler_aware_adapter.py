from __future__ import annotations

import asyncio
import re
from typing import Callable, List
from livekit.agents.stt import (
    STT,
    RecognizeStream,
    SpeechEvent,
    SpeechEventType,
    STTCapabilities,
)
from livekit import rtc

# Use the new config variable names
from .config import (
    IGNORED_FILLERS,
    INTERRUPTION_TRIGGERS,
    AGENT_SPEAKING_CONFIDENCE_THRESHOLD,
    SHORT_SEGMENT_TOKEN_LIMIT,
)


# ---------------------------- Helpers ----------------------------

# Regex to find word-like tokens
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

def _extract_words(text: str) -> List[str]:
    """Splits text into lowercase words."""
    return [w.lower() for w in _TOKEN_RE.findall(text or "")]

def _is_filler_only(words: List[str]) -> bool:
    """Checks if a list of words contains only ignored fillers."""
    return bool(words) and all(w in IGNORED_FILLERS for w in words)

def _has_interrupt_command(words: List[str]) -> bool:
    """Checks if a list of words contains an interruption command."""
    text = " ".join(words)
    
    # Check for multi-word commands first
    if any(cmd in text for cmd in INTERRUPTION_TRIGGERS if " " in cmd):
        return True
    
    # Check for single-word commands
    return any(w in INTERRUPTION_TRIGGERS for w in words)


# ---------------------------- Adapter ----------------------------

class FillerAwareAdapter(STT):
    """
    An STT wrapper that filters speech events to prevent filler words
    (e.g., 'uh', 'um') from interrupting the agent's speech.
    """

    def __init__(self, wrapped_stt: STT, agent_speaking_check: Callable[[], bool]):
        """
        Args:
            wrapped_stt: The base STT engine to wrap.
            agent_speaking_check: A callable that returns True if the agent is
                                  currently speaking, False otherwise.
        """
        super().__init__(
            capabilities=STTCapabilities(
                streaming=wrapped_stt.capabilities.streaming,
                interim_results=wrapped_stt.capabilities.interim_results,
                diarization=wrapped_stt.capabilities.diarization,
            )
        )
        self._base = wrapped_stt
        self._is_agent_speaking = agent_speaking_check

        # Forward events from the base STT
        wrapped_stt.on("metrics_collected",
                    lambda *a, **k: self.emit("metrics_collected", *a, **k))
        wrapped_stt.on("error",
                    lambda *a, **k: self.emit("error", *a, **k))

    @property
    def model(self) -> str:
        return f"FillerAwareAdapter({self._base.model})"

    @property
    def provider(self) -> str:
        return self._base.provider

    async def _recognize_impl(self, *args, **kwargs):
        return await self._base._recognize_impl(*args, **kwargs)

    def stream(self, *args, **kwargs) -> RecognizeStream:
        """Create a new recognition stream."""
        base_stream = self._base.stream(*args, **kwargs)
        return _FillerStream(self, base_stream, self._is_agent_speaking)

    async def aclose(self):
        await self._base.aclose()


class _FillerStream(RecognizeStream):
    """
    The stream implementation that applies the filtering logic.
    """
    def __init__(self, outer: STT, wrapped_stream: RecognizeStream, is_agent_speaking: Callable[[], bool]):
        super().__init__(
            stt=outer,
            conn_options=wrapped_stream._conn_options,
            sample_rate=getattr(wrapped_stream, "_needed_sr", None),
        )
        self._outer = outer
        self._base = wrapped_stream
        self._is_agent_speaking = is_agent_speaking

    async def _run(self):
        """Main task for processing audio and speech events."""
        
        # Task to forward input audio frames to the wrapped stream
        async def _forward_input():
            async for frame_or_flush in self._input_ch:
                if isinstance(frame_or_flush, rtc.AudioFrame):
                    self._base.push_frame(frame_or_flush)
                else:
                    self._base.flush()
            self._base.end_input()

        forward_task = asyncio.create_task(_forward_input())

        try:
            # Process events from the wrapped stream
            async with self._base:
                async for event in self._base:
                    filtered_event = self._filter_event(event)
                    if filtered_event is not None:
                        self._event_ch.send_nowait(filtered_event)
        finally:
            await forward_task

    # -------------------- Core Filtering Logic --------------------

    def _filter_event(self, event: SpeechEvent):
        """
        Applies the filtering logic to a single speech event.
        Returns the event if it should be kept, or None if suppressed.
        (Note: We return the event and set a flag to avoid suppression).
        """
        
        # 1. Always keep non-transcript events
        if event.type not in {
            SpeechEventType.INTERIM_TRANSCRIPT,
            SpeechEventType.PREFLIGHT_TRANSCRIPT,
            SpeechEventType.FINAL_TRANSCRIPT,
        }:
            return event

        if not event.alternatives:
            return event

        alt = event.alternatives[0]
        text = alt.text or ""
        words = _extract_words(text)

        if not words:
            return event

        # 2. Agent is NOT speaking? Keep everything.
        if not self._is_agent_speaking():
            return event

        # 3. Agent IS speaking. Apply suppression rules.

        # Rule A: Commands (e.g., "stop") always interrupt.
        if _has_interrupt_command(words):
            return event  # Allow interruption

        # Rule B: Pure filler (e.g., "uh", "umm") should NOT interrupt.
        if _is_filler_only(words):
            event._ignore_interruption = True  # Suppress interruption
            return event

        # Rule C: Low-confidence short segments should NOT interrupt.
        is_low_confidence = alt.confidence and alt.confidence < AGENT_SPEAKING_CONFIDENCE_THRESHOLD
        is_short = len(words) <= SHORT_SEGMENT_TOKEN_LIMIT
        
        if is_low_confidence and is_short:
            event._ignore_interruption = True  # Suppress interruption
            return event

        # 4. Default: Non-filler, non-command speech interrupts normally.
        return event