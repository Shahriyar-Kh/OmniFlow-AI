from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import edge_tts

from tbos_renderer.content_engine.schemas import ContentLanguage

LOGGER = logging.getLogger(__name__)

VOICE_MAP: dict[str, str] = {
    "roman_urdu": "ur-PK-UzmaNeural",
    "urdu": "ur-PK-UzmaNeural",
    "simple_english": "en-US-ChristopherNeural",
}
DEFAULT_VOICE = "en-US-ChristopherNeural"


@dataclass(frozen=True)
class VoiceoverResult:
    audio_path: str
    duration_seconds: float
    voice: str
    sha256: str
    size_bytes: int
    mime_type: str = "audio/mpeg"


@runtime_checkable
class VoiceoverEngine(Protocol):
    async def generate_voiceover(
        self,
        text: str,
        language: str | ContentLanguage,
        output_path: Path,
        *,
        voice: str | None = None,
    ) -> VoiceoverResult: ...


class EdgeTtsVoiceoverEngine:
    """Voiceover generation engine using Microsoft Edge TTS."""

    def __init__(self, default_voice: str = DEFAULT_VOICE) -> None:
        self.default_voice = default_voice

    def resolve_voice(self, language: str | ContentLanguage, override: str | None = None) -> str:
        if override:
            return override
        lang_key = (
            language.value if isinstance(language, ContentLanguage) else str(language).lower()
        )
        return VOICE_MAP.get(lang_key, self.default_voice)

    def probe_duration(self, audio_path: Path, fallback_word_count: int) -> float:
        """Probe exact audio duration using ffprobe if available, otherwise estimate."""
        ffprobe = shutil.which("ffprobe")
        if ffprobe and audio_path.exists():
            try:
                result = subprocess.run(
                    [
                        ffprobe,
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        str(audio_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return round(float(result.stdout.strip()), 2)
            except Exception as ex:
                LOGGER.warning("ffprobe failed to probe duration: %s", ex)
        # Approximate: ~150 words per minute -> 2.5 words per second
        estimated = max(1.0, round(fallback_word_count / 2.5, 2))
        return estimated

    async def generate_voiceover(
        self,
        text: str,
        language: str | ContentLanguage,
        output_path: Path,
        *,
        voice: str | None = None,
    ) -> VoiceoverResult:
        selected_voice = self.resolve_voice(language, voice)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        communicate = edge_tts.Communicate(text, selected_voice)
        await communicate.save(str(output_path))

        data = output_path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        duration = self.probe_duration(output_path, fallback_word_count=len(text.split()))

        return VoiceoverResult(
            audio_path=str(output_path),
            duration_seconds=duration,
            voice=selected_voice,
            sha256=sha256,
            size_bytes=len(data),
            mime_type="audio/mpeg",
        )
