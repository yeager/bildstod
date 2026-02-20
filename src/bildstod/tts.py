"""Text-to-speech with Piper (high quality) and espeak-ng (fallback).

Tries Piper first for natural-sounding Swedish and English speech,
falls back to espeak-ng if Piper is not available.

Piper voices are expected in ~/.local/share/piper-voices/ or
/usr/share/piper-voices/.

Usage:
    from bildschema.tts import speak
    speak("Hej!", lang="sv")
    speak("Hello!", lang="en")
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

# Piper voice model paths per language
PIPER_VOICES = {
    "sv": "sv_SE-nst-medium.onnx",
    "en": "en_US-amy-medium.onnx",
}

# espeak-ng voice names
ESPEAK_VOICES = {
    "sv": "sv",
    "en": "en",
}

_piper_path: str | None = None
_voice_dir: Path | None = None
_lock = threading.Lock()


def _find_piper() -> tuple[str | None, Path | None]:
    """Find piper binary and voice directory."""
    piper = shutil.which("piper")
    if not piper:
        return None, None

    # Search voice directories
    candidates = [
        Path.home() / ".local" / "share" / "piper-voices",
        Path("/usr/share/piper-voices"),
        Path("/usr/local/share/piper-voices"),
    ]
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        candidates.insert(0, Path(xdg) / "piper-voices")

    for d in candidates:
        if d.exists() and any(d.glob("*.onnx")):
            return piper, d

    return piper, None


def _get_piper() -> tuple[str | None, Path | None]:
    """Cached piper lookup."""
    global _piper_path, _voice_dir
    with _lock:
        if _piper_path is None:
            _piper_path, _voice_dir = _find_piper()
            if _piper_path is None:
                _piper_path = ""  # Mark as searched
    return (_piper_path or None), _voice_dir


def _play_wav(wav_path: str):
    """Play a WAV file using available player."""
    for player in ["aplay", "paplay", "pw-play", "ffplay"]:
        exe = shutil.which(player)
        if exe:
            args = [exe]
            if player == "ffplay":
                args += ["-nodisp", "-autoexit"]
            args.append(wav_path)
            try:
                subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                continue


def speak_piper(text: str, lang: str = "sv") -> bool:
    """Speak using Piper. Returns True if successful."""
    piper, voice_dir = _get_piper()
    if not piper or not voice_dir:
        return False

    voice_file = PIPER_VOICES.get(lang)
    if not voice_file:
        return False

    model_path = voice_dir / voice_file
    if not model_path.exists():
        return False

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        proc = subprocess.run(
            [piper, "--model", str(model_path),
             "--output_file", wav_path],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=10,
        )
        if proc.returncode == 0 and os.path.exists(wav_path):
            _play_wav(wav_path)
            # Clean up after a delay (let playback start)
            def cleanup():
                import time
                time.sleep(10)
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass
            threading.Thread(target=cleanup, daemon=True).start()
            return True
    except (subprocess.TimeoutExpired, OSError):
        pass
    return False


def speak_espeak(text: str, lang: str = "sv"):
    """Speak using espeak-ng (fallback)."""
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if not espeak:
        return
    voice = ESPEAK_VOICES.get(lang, lang)
    try:
        subprocess.Popen(
            [espeak, "-v", voice, "-s", "130", text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def speak(text: str, lang: str = "sv"):
    """Speak text using best available TTS engine.

    Tries Piper first (natural voice), falls back to espeak-ng.
    Runs in a background thread to avoid blocking the UI.
    """
    def _do_speak():
        if not speak_piper(text, lang):
            speak_espeak(text, lang)

    thread = threading.Thread(target=_do_speak, daemon=True)
    thread.start()


def get_tts_info() -> str:
    """Return info about available TTS for debug/about dialog."""
    piper, voice_dir = _get_piper()
    parts = []
    if piper and voice_dir:
        voices = list(voice_dir.glob("*.onnx"))
        parts.append(f"Piper ({len(voices)} voices)")
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak:
        parts.append(f"espeak-ng")
    return ", ".join(parts) if parts else "No TTS available"
