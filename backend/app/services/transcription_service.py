"""Video transcription service using Whisper (local).

Downloads video → transcribes with Whisper.
Supports: direct URLs, Google Drive links, Facebook/Instagram URLs (via yt-dlp).
"""

import logging
import os
import shutil
import tempfile
import time
import subprocess
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# Domains that need yt-dlp to extract the real video URL
_YTDLP_DOMAINS = [
    "facebook.com", "fb.com", "fb.watch",
    "instagram.com",
    "tiktok.com",
    "youtube.com", "youtu.be",
    "twitter.com", "x.com",
]


def _find_and_register_ffmpeg() -> str:
    """Find ffmpeg executable and add its directory to PATH if needed."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    candidates = [
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages",
        Path("C:/ffmpeg/bin"),
        Path("C:/Program Files/FFmpeg/bin"),
    ]
    for base in candidates:
        if base.exists():
            for ff in base.rglob("ffmpeg.exe"):
                ffmpeg_dir = str(ff.parent)
                if ffmpeg_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
                    logger.info("Added ffmpeg to PATH: %s", ffmpeg_dir)
                return str(ff)

    return "ffmpeg"


# Register ffmpeg on module load
_FFMPEG_BIN = _find_and_register_ffmpeg()

# Whisper model — "base" is a good balance of speed vs accuracy
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

_whisper_model = None


def _get_whisper_model():
    """Lazy-load Whisper model (downloads on first use, ~140MB for base)."""
    global _whisper_model
    if _whisper_model is None:
        import whisper
        logger.info("Loading Whisper model '%s'...", WHISPER_MODEL)
        _whisper_model = whisper.load_model(WHISPER_MODEL)
        logger.info("Whisper model loaded.")
    return _whisper_model


def _needs_ytdlp(url: str) -> bool:
    """Check if URL needs yt-dlp to extract the real video/audio URL."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in _YTDLP_DOMAINS)


def _download_with_ytdlp(url: str, dest_path: str) -> str:
    """Use yt-dlp to download video/audio from social media platforms.

    Prefers format with audio. Falls back to best available.
    Returns path to downloaded file.
    """
    import yt_dlp

    logger.info("Using yt-dlp to extract video from: %s", url[:80])

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": dest_path,
        # Prefer format with audio; if separate, merge
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "merge_output_format": "mp4",
        # Don't post-process (we just need audio for Whisper)
        "postprocessors": [],
    }

    # Pass cookies for platforms requiring auth (Facebook, Instagram, etc.)
    if settings.YTDLP_COOKIES_FROM_BROWSER:
        ydl_opts["cookiesfrombrowser"] = (settings.YTDLP_COOKIES_FROM_BROWSER,)
    elif settings.YTDLP_COOKIES_FILE:
        ydl_opts["cookiefile"] = settings.YTDLP_COOKIES_FILE

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        duration = info.get("duration", 0)
        title = info.get("title", "unknown")
        logger.info(
            "yt-dlp downloaded: %s (%.0fs)",
            title[:60] if isinstance(title, str) else "?",
            duration or 0,
        )

    # yt-dlp may add extension to dest_path
    if os.path.exists(dest_path):
        return dest_path
    # Check common extensions
    for ext in [".mp4", ".m4a", ".webm", ".mp3"]:
        candidate = dest_path + ext
        if os.path.exists(candidate):
            return candidate
    # Check any file in the directory
    parent = os.path.dirname(dest_path)
    files = os.listdir(parent)
    if files:
        return os.path.join(parent, files[0])

    raise FileNotFoundError(f"yt-dlp did not produce output file at {dest_path}")


def _download_direct(url: str, dest_path: str) -> str:
    """Download video from direct URL (CDN, Google Drive, etc.)."""
    import requests

    # Handle Google Drive share links
    if "drive.google.com" in url:
        file_id = None
        if "/file/d/" in url:
            file_id = url.split("/file/d/")[1].split("/")[0]
        elif "id=" in url:
            file_id = url.split("id=")[1].split("&")[0]
        if file_id:
            url = f"https://drive.google.com/uc?export=download&id={file_id}"

    logger.info("Downloading from: %s", url[:100])
    resp = requests.get(url, stream=True, timeout=120, allow_redirects=True)
    resp.raise_for_status()

    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    file_size = os.path.getsize(dest_path)
    logger.info("Downloaded %.1f MB", file_size / 1024 / 1024)
    return dest_path


def transcribe_video(video_url: str) -> dict:
    """Full pipeline: download → transcribe.

    Automatically detects Facebook/Instagram/TikTok URLs and uses yt-dlp.
    For direct URLs, downloads with requests.

    Returns:
        {
            "transcript": "full text...",
            "language": "en",
            "segments": [{"start": 0.0, "end": 2.5, "text": "..."}],
            "duration_seconds": 30.5,
            "processing_time": 12.3,
        }
    """
    start_time = time.time()

    with tempfile.TemporaryDirectory(prefix="whisper_") as tmpdir:
        # Step 1: Download video/audio
        if _needs_ytdlp(video_url):
            media_path = _download_with_ytdlp(
                video_url, os.path.join(tmpdir, "media")
            )
        else:
            media_path = os.path.join(tmpdir, "media.mp4")
            _download_direct(video_url, media_path)

        # Step 2: Transcribe with Whisper
        model = _get_whisper_model()
        logger.info("Transcribing with Whisper '%s'...", WHISPER_MODEL)
        result = model.transcribe(
            media_path,
            fp16=False,  # CPU-friendly
            verbose=False,
        )

    processing_time = time.time() - start_time

    # Extract segments
    segments = []
    for seg in result.get("segments", []):
        segments.append({
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "text": seg["text"].strip(),
        })

    transcript = result["text"].strip()
    language = result.get("language", "unknown")

    logger.info(
        "Transcription complete: %d chars, language=%s, %.1fs processing",
        len(transcript), language, processing_time,
    )

    return {
        "transcript": transcript,
        "language": language,
        "segments": segments,
        "duration_seconds": segments[-1]["end"] if segments else 0,
        "processing_time": processing_time,
    }
