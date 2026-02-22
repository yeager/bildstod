"""Phonetics/TTS support using Piper (preferred) or espeak-ng."""
import subprocess
import shutil
import os
import tempfile


def has_piper():
    """Check if Piper TTS is available."""
    return shutil.which('piper') is not None


def has_espeak():
    """Check if espeak-ng is available."""
    return shutil.which('espeak-ng') is not None


def speak(text, lang='sv', engine=None):
    """Speak text using Piper (first) or espeak-ng (fallback).
    
    Args:
        text: Text to speak
        lang: Language code (default: sv for Swedish)
        engine: Force 'piper' or 'espeak'. None = auto-detect.
    """
    if not text:
        return

    if engine is None:
        engine = 'piper' if has_piper() else 'espeak' if has_espeak() else None

    if engine == 'piper':
        _speak_piper(text, lang)
    elif engine == 'espeak':
        _speak_espeak(text, lang)


def _speak_piper(text, lang):
    """Speak using Piper TTS."""
    try:
        # Find Piper model
        model_dir = os.path.expanduser('~/.local/share/piper/voices')
        model = None
        if os.path.isdir(model_dir):
            for f in os.listdir(model_dir):
                if f.startswith(lang) and f.endswith('.onnx'):
                    model = os.path.join(model_dir, f)
                    break

        cmd = ['piper', '--output-raw']
        if model:
            cmd.extend(['--model', model])

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = tmp.name

        proc = subprocess.Popen(
            ['piper', '--output_file', tmp_path] + (['--model', model] if model else []),
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        proc.communicate(input=text.encode('utf-8'))

        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            subprocess.Popen(
                ['paplay', tmp_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except (FileNotFoundError, OSError):
        _speak_espeak(text, lang)


def _speak_espeak(text, lang):
    """Speak using espeak-ng (fallback)."""
    try:
        subprocess.Popen(
            ['espeak-ng', '-v', lang, text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except (FileNotFoundError, OSError):
        pass


def get_phonetics(word, lang='sv'):
    """Get IPA phonetic transcription of a word."""
    try:
        result = subprocess.run(
            ['espeak-ng', '-v', lang, '--ipa', '-q', word],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ''
