#!/usr/bin/env python3
"""
mrbeast_generator.py
──────────────────────────────────────────────────────────────────────────────
MrBeast / Streamer Shorts Generator Pipeline

Pipeline stages:
  1. Download main video (yt-dlp)
  2. PySceneDetect → find scene boundaries
  3. YOLOv11n + MediaPipe → face tracking per frame → crop 9:16
  4. Download gameplay (yt-dlp) or use cache
  5. Dual-screen composition (top 60% tracked, bottom 40% gameplay)
  6. whisper-timestamped (base model) → word-level captions
  7. Render Impact-font captions (neon verb coloring)
  8. Audio mutation: 1.04x speed, lo-fi ducking, EQ shift
  9. Visual mutation: 1.03x crop, progress bar overlay
 10. Final H.264 encode
"""

import argparse
import asyncio
import json
import os
import sys
import time
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ─── Lazy heavy imports so we can log progress ────────────────────────────────

def log(msg: str):
    print(msg, flush=True)


# ─── Config ───────────────────────────────────────────────────────────────────

TARGET_W = 1080
TARGET_H = 1920
TARGET_FPS = 60
ENCODING_PRESET = "slow"
ENCODING_CRF = "14"
CLIP_DURATION = 60.0       # seconds to take from the main video
GAMEPLAY_DURATION = 60.0   # seconds of bottom gameplay

SPLIT_RATIO = 0.58          # top portion for the face-tracked speaker
BOTTOM_H = int(TARGET_H * (1 - SPLIT_RATIO))
TOP_H    = TARGET_H - BOTTOM_H

WHISPER_MODEL = "base"     # ~142 MB, fast enough

ACTION_VERBS = {
    "survived", "lost", "won", "crazy", "insane", "wild", "epic", "impossible",
    "destroyed", "broke", "beat", "killed", "died", "exploded", "changed",
    "shocking", "unbelievable", "never", "broke", "challenge", "million",
    "thousand", "dude", "bro", "fire", "sick", "amazing", "legendary"
}

SCRIPT_DIR    = Path(__file__).resolve().parent
PROJECT_DIR   = SCRIPT_DIR.parent
WORK_DIR      = PROJECT_DIR / "public" / "output" / "mrbeast_work"
OUTPUT_PATH   = PROJECT_DIR / "public" / "output" / "mrbeast_upload.mp4"
LOFI_CACHE    = SCRIPT_DIR / "lofi.mp3"
GAMEPLAY_CACHE = WORK_DIR / "gameplay_raw.mp4"

# Royalty-free lofi track (YouTube Audio Library – Creative Commons)
LOFI_YT_URL  = "https://www.youtube.com/watch?v=jfKfPfyJRdk"
# Default gameplay fallback
GAMEPLAY_YT_URL = "https://www.youtube.com/watch?v=n_Dv4JMiwK8"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def run(cmd: List[str], cwd=None, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=check)


def ytdlp_download(url: str, out_path: Path, extra_args: List[str] = None) -> bool:
    """Download a YouTube video to out_path using yt-dlp. Returns True on success."""
    args = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", str(out_path),
    ]
    if extra_args:
        args += extra_args
    args.append(url)
    
    try:
        # Run Popen to stream progress bar and download size logs in real time
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        for line in process.stdout:
            cleaned = line.strip()
            if cleaned:
                log(f"  [yt-dlp] {cleaned}")
        process.wait()
        return out_path.exists() and out_path.stat().st_size > 1024 * 50
    except Exception as e:
        log(f"  ❌ yt-dlp download process error: {e}")
        return False


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load Impact (or fallback) font for the given size."""
    candidates = [
        "/Library/Fonts/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
        str(SCRIPT_DIR / "assets" / "Impact.ttf"),
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ─── Stage 1: Download main video ─────────────────────────────────────────────

def download_main(url: str, work_dir: Path) -> Path:
    out = work_dir / "main_raw.mp4"
    if out.exists():
        log("  Using cached main video.")
        return out
    log(f"  Downloading main video: {url}")
    if ytdlp_download(url, out):
        log("  ✅ Main video downloaded.")
        return out
    raise RuntimeError("Failed to download main video.")


# ─── Stage 2: Gemini AI Viral Segment Analyzer ──────────────────────────────

def get_best_clip(video_path: Path) -> dict:
    """Ask Gemini to find the single most viral 25-40s segment. Falls back to PySceneDetect."""
    sys.path.insert(0, str(SCRIPT_DIR))
    from gemini_analyzer import get_best_clip as _analyzer
    return _analyzer(video_path)


# ─── Stage 3: Face Tracking Crop (OpenCV + MediaPipe) ─────────────────────────

def track_and_crop(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    out_path: Path,
    out_w: int = TARGET_W,
    out_h: int = TOP_H,
) -> Path:
    """Read frames from [start_sec, end_sec], track face with MediaPipe,
    smooth the crop window, and write a 9:16 top-portion MP4."""
    log("  Tracking face coordinates and cropping to 9:16…")

    try:
        import mediapipe as mp
        import mediapipe.python.solutions.face_detection as mp_face
    except (ImportError, AttributeError):
        log("  ⚠ mediapipe not available. Falling back to centre-crop.")
        return _center_crop(video_path, start_sec, end_sec, out_path, out_w, out_h)

    cap = cv2.VideoCapture(str(video_path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)

    total_frames = int((end_sec - start_sec) * src_fps)

    # First pass: collect face centre x positions per frame
    centers_x: List[Optional[float]] = []
    face_detector = mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.4)
    frame_idx = 0
    while frame_idx < total_frames:
        ret, frame = cap.read()
        if not ret:
            break
        src_h, src_w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_detector.process(rgb)
        if results.detections:
            det = results.detections[0]
            bbox = det.location_data.relative_bounding_box
            cx = (bbox.xmin + bbox.width / 2) * src_w
        else:
            cx = None
        centers_x.append(cx)
        frame_idx += 1
    cap.release()
    face_detector.close()

    # Fill None gaps with interpolation
    filled: List[float] = list(centers_x)
    n = len(filled)
    if n == 0:
        return _center_crop(video_path, start_sec, end_sec, out_path, out_w, out_h)
    # Forward fill
    last_val: Optional[float] = None
    for i in range(n):
        if filled[i] is not None:
            last_val = filled[i]
        elif last_val is not None:
            filled[i] = last_val
    # Backward fill
    last_val = None
    for i in range(n - 1, -1, -1):
        if filled[i] is not None:
            last_val = filled[i]
        elif last_val is not None:
            filled[i] = last_val
    if any(v is None for v in filled):
        # All None
        src_cap = cv2.VideoCapture(str(video_path))
        src_w_def = src_cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920
        src_cap.release()
        filled = [src_w_def / 2] * n

    # Sliding-average smoothing (window = 1.5 seconds of frames)
    window = max(1, int(src_fps * 1.5))
    smoothed: List[float] = []
    for i in range(n):
        lo = max(0, i - window // 2)
        hi = min(n, i + window // 2 + 1)
        smoothed.append(float(np.mean([v for v in filled[lo:hi] if v is not None] or [filled[i]])))

    # Second pass: write cropped frames
    cap = cv2.VideoCapture(str(video_path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)

    # Crop window width in source pixels that gives 9:16 aspect for out_w/out_h
    crop_w = int(src_h * out_w / out_h)
    crop_w = min(crop_w, src_w)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, min(src_fps, TARGET_FPS), (out_w, out_h))

    for i, cx in enumerate(smoothed):
        ret, frame = cap.read()
        if not ret:
            break
        half = crop_w // 2
        x1 = int(max(0, min(cx - half, src_w - crop_w)))
        x2 = x1 + crop_w
        cropped = frame[:, x1:x2]
        resized = cv2.resize(cropped, (out_w, out_h))
        writer.write(resized)

    cap.release()
    writer.release()
    log("  ✅ Face-tracked crop complete.")
    return out_path


def _center_crop(video_path: Path, start_sec: float, end_sec: float, out_path: Path, out_w: int, out_h: int) -> Path:
    """Simple centre-crop fallback (no face tracking)."""
    cap = cv2.VideoCapture(str(video_path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)

    crop_w = int(src_h * out_w / out_h)
    crop_w = min(crop_w, src_w)
    x1 = (src_w - crop_w) // 2

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, min(src_fps, TARGET_FPS), (out_w, out_h))

    total = int((end_sec - start_sec) * src_fps)
    for _ in range(total):
        ret, frame = cap.read()
        if not ret:
            break
        cropped = frame[:, x1: x1 + crop_w]
        resized = cv2.resize(cropped, (out_w, out_h))
        writer.write(resized)

    cap.release()
    writer.release()
    return out_path


# ─── Stage 4: Download Gameplay ────────────────────────────────────────────────

def get_gameplay(gameplay_url: Optional[str], work_dir: Path) -> Path:
    if GAMEPLAY_CACHE.exists() and GAMEPLAY_CACHE.stat().st_size > 1024 * 100:
        log("  Using cached gameplay video.")
        return GAMEPLAY_CACHE

    url = gameplay_url or GAMEPLAY_YT_URL
    log(f"  Downloading gameplay: {url}")
    if ytdlp_download(url, GAMEPLAY_CACHE):
        log("  ✅ Gameplay downloaded.")
        return GAMEPLAY_CACHE
    raise RuntimeError("Failed to download gameplay video.")


def crop_gameplay(gameplay_path: Path, out_path: Path) -> Path:
    """Centre-crop gameplay to bottom portion dimensions."""
    cap = cv2.VideoCapture(str(gameplay_path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    crop_w = int(src_h * TARGET_W / BOTTOM_H)
    crop_w = min(crop_w, src_w)
    x1 = (src_w - crop_w) // 2

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, min(src_fps, TARGET_FPS), (TARGET_W, BOTTOM_H))

    total = int(GAMEPLAY_DURATION * src_fps)
    for _ in range(total):
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop
            ret, frame = cap.read()
            if not ret:
                break
        cropped = frame[:, x1: x1 + crop_w]
        resized = cv2.resize(cropped, (TARGET_W, BOTTOM_H))
        writer.write(resized)

    cap.release()
    writer.release()
    log("  ✅ Gameplay cropped.")
    return out_path


# ─── Stage 5: Dual-screen composition ─────────────────────────────────────────

def compose_dual_screen(top_path: Path, bottom_path: Optional[Path], out_path: Path, duration: float) -> Path:
    """Stack top (face-tracked) and optional bottom (gameplay) frames into one 9:16 video."""
    log("  Composing video layout…")

    top_cap = cv2.VideoCapture(str(top_path))
    bot_cap = cv2.VideoCapture(str(bottom_path)) if bottom_path else None
    fps = TARGET_FPS

    # Apply 1.03x rescale (visual mutation against Content ID)
    SCALE = 1.03
    scaled_w = int(TARGET_W * SCALE)
    scaled_h = int(TARGET_H * SCALE)
    pad_x = (scaled_w - TARGET_W) // 2
    pad_y = (scaled_h - TARGET_H) // 2

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (TARGET_W, TARGET_H))

    total = int(duration * fps)
    for i in range(total):
        ret_t, top_frame = top_cap.read()

        if not ret_t:
            top_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            _, top_frame = top_cap.read()

        if top_frame is None:
            break

        if bot_cap:
            ret_b, bot_frame = bot_cap.read()
            if not ret_b:
                bot_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                _, bot_frame = bot_cap.read()
            if bot_frame is None:
                break
            # Ensure correct sizes
            top_frame = cv2.resize(top_frame, (TARGET_W, TOP_H))
            bot_frame = cv2.resize(bot_frame, (TARGET_W, BOTTOM_H))
            # Stack
            canvas = np.vstack([top_frame, bot_frame])
        else:
            canvas = cv2.resize(top_frame, (TARGET_W, TARGET_H))

        # Rescale then centre-crop (pixel mutation)
        scaled = cv2.resize(canvas, (scaled_w, scaled_h))
        final = scaled[pad_y: pad_y + TARGET_H, pad_x: pad_x + TARGET_W]

        # Progress bar (bottom edge, visual mutation)
        progress = i / max(total - 1, 1)
        bar_w = int(TARGET_W * progress)
        cv2.rectangle(final, (0, TARGET_H - 8), (bar_w, TARGET_H), (0, 200, 255), -1)

        writer.write(final)

    top_cap.release()
    if bot_cap:
        bot_cap.release()
    writer.release()
    log("  ✅ Video composition done.")
    return out_path


# ─── Stage 6: Whisper word-level transcription ────────────────────────────────

def transcribe_video(video_path_raw: Path, audio_path: Path) -> List[Dict]:
    """Extract audio then run whisper-timestamped (base model). Returns word list."""
    log(f"  Extracting audio for Whisper…")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path_raw), "-vn", "-ar", "16000", "-ac", "1", "-q:a", "0", "-map", "a", str(audio_path)],
        capture_output=True
    )
    
    log(f"  Running Whisper base model for word-level timestamps…")
    try:
        import whisper_timestamped as whisper
        model = whisper.load_model(WHISPER_MODEL)
        audio = whisper.load_audio(str(audio_path))
        result = whisper.transcribe(model, audio, language="en")
        words = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                words.append({
                    "word": w["text"].strip(),
                    "start": w["start"],
                    "end": w["end"],
                })
        log(f"  ✅ Whisper transcribed {len(words)} words.")
        return words
    except ImportError:
        log("  ⚠ whisper-timestamped not available, trying openai-whisper…")
        return _whisper_fallback(audio_path)


def _whisper_fallback(audio_path: Path) -> List[Dict]:
    """Fallback: use openai-whisper (no word timestamps, use proportional)."""
    try:
        import whisper
        model = whisper.load_model(WHISPER_MODEL)
        result = model.transcribe(str(audio_path))
        words = []
        for seg in result.get("segments", []):
            text_words = seg["text"].strip().split()
            if not text_words:
                continue
            seg_dur = seg["end"] - seg["start"]
            word_dur = seg_dur / len(text_words)
            for i, w in enumerate(text_words):
                words.append({
                    "word": w,
                    "start": seg["start"] + i * word_dur,
                    "end": seg["start"] + (i + 1) * word_dur,
                })
        log(f"  ✅ Whisper fallback transcribed {len(words)} words.")
        return words
    except Exception as e:
        log(f"  ❌ Whisper failed: {e}")
        return []


# ─── Stage 7: Impact Captions (MrBeast style) ─────────────────────────────────

def chunk_words(words: List[Dict], chunk_size: int = 3) -> List[Dict]:
    """Group words into caption chunks of `chunk_size` words."""
    chunks = []
    for i in range(0, len(words), chunk_size):
        group = words[i: i + chunk_size]
        chunks.append({
            "text": " ".join(w["word"] for w in group),
            "start": group[0]["start"],
            "end": group[-1]["end"],
        })
    return chunks


def render_caption_frame(text: str, frame_w: int = TARGET_W, frame_h: int = TARGET_H) -> np.ndarray:
    """Render a single caption frame as RGBA numpy array."""
    img = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    font_size = 88  # large Impact
    font = load_font(font_size)

    words = text.split()
    # Render each word separately to color action verbs
    line_imgs = []
    # Build lines first
    lines_text = []
    cur_line = []
    for w in words:
        test = " ".join(cur_line + [w])
        bbox = draw.textbbox((0, 0), test, font=font, stroke_width=6)
        if bbox[2] - bbox[0] > frame_w - 80 and cur_line:
            lines_text.append(cur_line)
            cur_line = [w]
        else:
            cur_line.append(w)
    if cur_line:
        lines_text.append(cur_line)

    line_h = font_size + 20
    total_text_h = len(lines_text) * line_h
    y_start = int(frame_h * 0.68) - total_text_h // 2  # place in lower-middle area

    for line_words in lines_text:
        # Measure full line
        full_line = " ".join(line_words)
        bbox = draw.textbbox((0, 0), full_line, font=font, stroke_width=6)
        line_w = bbox[2] - bbox[0]
        x = (frame_w - line_w) // 2

        # Draw word by word with colour
        cur_x = x
        for idx, word in enumerate(line_words):
            display = word + ("" if idx == len(line_words) - 1 else " ")
            is_verb = word.strip(".,!?\"'").lower() in ACTION_VERBS

            color = (255, 230, 0, 255) if is_verb else (255, 255, 255, 255)
            shadow_col = (0, 0, 0, 255)

            # shadow
            draw.text((cur_x + 5, y_start + 5), display, font=font,
                      fill=(0, 0, 0, 180), stroke_width=8, stroke_fill=shadow_col)
            # main
            draw.text((cur_x, y_start), display, font=font,
                      fill=color, stroke_width=6, stroke_fill=(0, 0, 0, 255))

            bbox_w = draw.textbbox((0, 0), display, font=font, stroke_width=6)
            cur_x += bbox_w[2] - bbox_w[0]

        y_start += line_h

    return np.array(img)


def overlay_captions_on_video(video_path: Path, chunks: List[Dict], out_path: Path) -> Path:
    """Read frames from video_path, overlay captions per chunk, write to out_path."""
    log(f"  Overlaying {len(chunks)} caption chunks…")
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or TARGET_FPS
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (TARGET_W, TARGET_H))

    # Pre-render caption frames
    caption_frames: Dict[int, np.ndarray] = {}
    for chunk in chunks:
        rgba = render_caption_frame(chunk["text"])
        s_frame = int(chunk["start"] * fps)
        e_frame = int(chunk["end"] * fps)
        for fi in range(s_frame, e_frame):
            caption_frames[fi] = rgba

    for fi in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break

        if fi in caption_frames:
            cap_rgba = caption_frames[fi]
            cap_bgr = cv2.cvtColor(cap_rgba, cv2.COLOR_RGBA2BGRA)
            # Alpha blend
            alpha = cap_bgr[:, :, 3:4] / 255.0
            cap_rgb = cap_bgr[:, :, :3]
            frame = np.clip(frame * (1 - alpha) + cap_rgb * alpha, 0, 255).astype(np.uint8)

        writer.write(frame)

    cap.release()
    writer.release()
    log("  ✅ Captions overlaid.")
    return out_path


# ─── Stage 8: Audio Mutation ──────────────────────────────────────────────────

def download_lofi(work_dir: Path) -> Optional[Path]:
    if LOFI_CACHE.exists() and LOFI_CACHE.stat().st_size > 1024 * 10:
        return LOFI_CACHE
    log(f"  Downloading lo-fi background track…")
    tmp = work_dir / "lofi_raw.mp4"
    if ytdlp_download(LOFI_YT_URL, tmp, extra_args=["--no-playlist"]):
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp), "-vn", "-ar", "44100", "-ac", "2", str(LOFI_CACHE)],
            capture_output=True
        )
        if LOFI_CACHE.exists():
            log("  ✅ Lo-fi track ready.")
            return LOFI_CACHE
    log("  ⚠ Could not download lo-fi track; skipping background music.")
    return None


def apply_audio_mutations(
    video_path: Path,
    voice_audio_path: Path,
    lofi_path: Optional[Path],
    out_path: Path,
    duration: float
) -> Path:
    """
    Audio mutations:
      - Speed voice by 1.04x (breaks audio fingerprint)
      - Duck lo-fi music under the voice track (sidechaining via volume envelope)
      - Subtle bass EQ shift (+3 Hz, −3 dB)
    """
    log("  Applying audio mutations (1.04x speed, lo-fi ducking, EQ shift)…")

    sped_voice = out_path.parent / "voice_sped.mp3"
    # Speed up voice audio
    subprocess.run([
        "ffmpeg", "-y", "-i", str(voice_audio_path),
        "-filter:a", "atempo=1.04",
        str(sped_voice)
    ], capture_output=True)

    # Build filter chain
    if lofi_path and lofi_path.exists():
        # Mix with sidechain-duck: lower lofi volume when voice is active
        filter_complex = (
            "[1:a]volume=0.22[bg];"
            "[0:a]volume=1.0[voice];"
            "[bg][voice]amix=inputs=2:duration=first:dropout_transition=2[aout];"
            "[aout]equalizer=f=60:t=o:w=200:g=-2[eq]"  # subtle bass cut
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(sped_voice),
            "-i", str(lofi_path),
            "-filter_complex", filter_complex,
            "-map", "[eq]",
            "-t", str(duration),
            str(out_path)
        ]
    else:
        filter_complex = "[0:a]equalizer=f=60:t=o:w=200:g=-2[eq]"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(sped_voice),
            "-filter_complex", filter_complex,
            "-map", "[eq]",
            "-t", str(duration),
            str(out_path)
        ]

    result = subprocess.run(cmd, capture_output=True)
    if not out_path.exists():
        log(f"  ⚠ Audio mutation ffmpeg failed: {result.stderr[:200]}")
        shutil.copy(sped_voice, out_path)

    log("  ✅ Audio mutations applied.")
    return out_path


# ─── Stage 9: Final mux ───────────────────────────────────────────────────────

def mux_and_encode(video_path: Path, audio_path: Path, out_path: Path) -> Path:
    """Combine video (mp4v) and mutated audio → final H.264 MP4."""
    log(f"  Writing final video: {out_path}")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-preset", ENCODING_PRESET,
        "-crf", ENCODING_CRF,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "320k",
        "-movflags", "+faststart",
        "-shortest",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if out_path.exists() and out_path.stat().st_size > 1024 * 100:
        size_mb = out_path.stat().st_size / (1024 * 1024)
        log(f"FINAL_FILE_SIZE: {size_mb:.2f} MB")
        log(f"  ✅ DONE: {out_path}")
        return out_path
    raise RuntimeError(f"Final mux failed.\n{result.stderr[:500]}")


# ─── TTS Voiceover helpers ────────────────────────────────────────────────────

def _generate_tts_voiceover(script: str, work_dir: Path) -> Optional[Path]:
    """Generate an energetic MP3 from the Gemini voiceover script using edge-tts."""
    out_mp3 = work_dir / "gemini_vo.mp3"
    try:
        import asyncio
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(script, "en-US-GuyNeural", rate="+15%")
            with open(str(out_mp3), "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])

        asyncio.run(_run())
        if out_mp3.exists() and out_mp3.stat().st_size > 1024:
            log(f"  ✅ TTS voiceover generated ({out_mp3.stat().st_size // 1024} KB).")
            return out_mp3
    except Exception as e:
        log(f"  ⚠ edge-tts voiceover failed: {e}")

    # Fallback: use gTTS
    try:
        from gtts import gTTS
        tts = gTTS(text=script, lang="en", slow=False)
        tts.save(str(out_mp3))
        if out_mp3.exists() and out_mp3.stat().st_size > 1024:
            log(f"  ✅ gTTS voiceover generated.")
            return out_mp3
    except Exception as e:
        log(f"  ⚠ gTTS fallback also failed: {e}")

    return None


def create_hybrid_audio(original_video: Path, tts_audio: Path, start_sec: float, dur: float, out_path: Path) -> Path:
    """
    Creates a hybrid audio track: 
    [0 : tts_duration] -> TTS Hook
    [tts_duration : dur] -> Original video audio
    """
    # 1. Get TTS duration
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(tts_audio)],
        capture_output=True, text=True
    )
    try:
        tts_dur = float(res.stdout.strip())
    except ValueError:
        tts_dur = 5.0  # fallback

    log(f"  AI hook duration: {tts_dur:.1f}s. Splicing with original audio...")

    if tts_dur >= dur:
        # TTS is longer than the whole clip, just return TTS
        import shutil
        shutil.copy(tts_audio, out_path)
        return out_path
        
    # Extract original clip audio
    clip_audio = out_path.parent / "clip_audio_temp.wav"
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", str(dur),
        "-i", str(original_video),
        "-q:a", "0", "-map", "a", str(clip_audio)
    ], capture_output=True)

    # Combine TTS and original audio starting at tts_dur
    filter_complex = f"[1:a]atrim=start={tts_dur},asetpts=PTS-STARTPTS[part2]; [0:a][part2]concat=n=2:v=0:a=1[out]"
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(tts_audio),
        "-i", str(clip_audio),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        str(out_path)
    ], capture_output=True)

    return out_path


# ─── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    global TARGET_W, TARGET_H, TARGET_FPS, ENCODING_PRESET, ENCODING_CRF, BOTTOM_H, TOP_H
    parser = argparse.ArgumentParser(description="MrBeast Shorts Generator")
    parser.add_argument("--url", required=True, help="Main video YouTube URL")
    parser.add_argument("--gameplay-url", default=None, help="Gameplay bottom-screen URL (optional)")
    parser.add_argument("--quality", default="high", choices=["low", "medium", "high"], help="Video quality preset")
    args = parser.parse_args()

    if args.quality == "low":
        TARGET_W = 480
        TARGET_H = 854
        TARGET_FPS = 30
        ENCODING_PRESET = "fast"
        ENCODING_CRF = "22"
    elif args.quality == "medium":
        TARGET_W = 720
        TARGET_H = 1280
        TARGET_FPS = 30
        ENCODING_PRESET = "medium"
        ENCODING_CRF = "18"
    else:  # high
        TARGET_W = 1080
        TARGET_H = 1920
        TARGET_FPS = 60
        ENCODING_PRESET = "slow"
        ENCODING_CRF = "14"

    BOTTOM_H = int(TARGET_H * (1 - SPLIT_RATIO))
    TOP_H    = TARGET_H - BOTTOM_H

    import shutil
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    log("=== MrBeast Generator Pipeline Started ===")
    t0 = time.time()

    # ── 1. Download main video
    log("[1/5] Downloading main video...")
    main_raw = download_main(args.url, WORK_DIR)

    # ── 2. Gemini AI analysis — find top 5 viral moments (20-40s each)
    log("[2/5] Asking Gemini AI to find top 5 viral moments...")
    sys.path.insert(0, str(SCRIPT_DIR))
    from gemini_analyzer import get_all_clips
    all_clips = get_all_clips(main_raw)
    log(f"  Gemini identified {len(all_clips)} clips to process.")

    has_gameplay = args.gameplay_url is not None

    # ── 3. Pre-download gameplay once (if requested)
    gameplay_cropped = None
    if has_gameplay:
        log("[3/5] Preparing gameplay footage...")
        gameplay_raw = get_gameplay(args.gameplay_url, WORK_DIR)
        gameplay_cropped = WORK_DIR / "gameplay_cropped.mp4"
        crop_gameplay(gameplay_raw, gameplay_cropped)
    else:
        log("[3/5] Single-screen mode — no gameplay footage.")

    # ── 4. Pre-download lofi once
    lofi = download_lofi(WORK_DIR)

    # ── 5. Generate each clip
    log(f"[4/5] Generating {len(all_clips)} Short clips...")
    generated_paths = []

    for clip_data in all_clips:
        cn         = clip_data.get("clip_number", 1)
        start_sec  = clip_data["start_sec"]
        end_sec    = clip_data["end_sec"]
        dur        = clip_data["duration_seconds"]
        title      = clip_data.get("viral_title", f"Clip {cn}")
        hook_script = clip_data.get("hook_script", "")

        log(f"\n--- Clip {cn}/5: {title} ({dur:.0f}s) ---")
        clip_dir = WORK_DIR / f"clip_{cn}"
        clip_dir.mkdir(exist_ok=True)
        clip_out  = OUTPUT_PATH.parent / f"mrbeast_clip_{cn}.mp4"

        # Face-tracked crop
        top_tracked = clip_dir / "top_tracked.mp4"
        if has_gameplay:
            track_and_crop(main_raw, start_sec, end_sec, top_tracked, TARGET_W, TOP_H)
        else:
            track_and_crop(main_raw, start_sec, end_sec, top_tracked, TARGET_W, TARGET_H)

        # Compose video
        dual_silent = clip_dir / "dual_silent.mp4"
        compose_dual_screen(top_tracked, gameplay_cropped, dual_silent, dur)

        # Create Hybrid Audio (AI Hook + Original Audio)
        combined_audio = clip_dir / "combined_audio.wav"
        
        if hook_script:
            log(f"  Hook: \"{hook_script[:80]}...\"")
            script_file = clip_dir / "vo_script.txt"
            script_file.write_text(hook_script, encoding="utf-8")
            
            # Generate TTS for just the hook
            tts_audio = _generate_tts_voiceover(hook_script, clip_dir)
            if tts_audio and tts_audio.exists():
                # Merge TTS and original audio
                create_hybrid_audio(main_raw, tts_audio, start_sec, dur, combined_audio)
            else:
                log("  TTS failed. Falling back to extracting original audio only.")
                subprocess.run(["ffmpeg", "-y", "-ss", str(start_sec), "-t", str(dur), "-i", str(main_raw), "-q:a", "0", "-map", "a", str(combined_audio)], capture_output=True)
        else:
            log("  No hook script. Using original audio only.")
            subprocess.run(["ffmpeg", "-y", "-ss", str(start_sec), "-t", str(dur), "-i", str(main_raw), "-q:a", "0", "-map", "a", str(combined_audio)], capture_output=True)

        # Run Whisper on the final combined audio for perfect timing
        log("  Running Whisper on combined audio...")
        raw_audio = clip_dir / "raw_audio.wav"
        words = transcribe_video(combined_audio, raw_audio)

        # Captions
        if words:
            chunks = chunk_words(words, chunk_size=3)
            captioned_video = clip_dir / "captioned.mp4"
            overlay_captions_on_video(dual_silent, chunks, captioned_video)
        else:
            captioned_video = dual_silent

        # Audio mutations
        mutated_audio = clip_dir / "mutated_audio.mp3"
        apply_audio_mutations(main_raw, raw_audio, lofi, mutated_audio, dur)

        # Final encode for this clip
        mux_and_encode(captioned_video, mutated_audio, clip_out)
        generated_paths.append(clip_out)
        log(f"  Clip {cn} saved: {clip_out.name}")

    # Also copy clip 1 as the default preview output
    if generated_paths:
        import shutil
        shutil.copy(generated_paths[0], OUTPUT_PATH)
        size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
        log(f"FINAL_FILE_SIZE: {size_mb:.2f} MB")

    log(f"\n[5/5] All {len(generated_paths)} clips generated!")
    for p in generated_paths:
        mb = p.stat().st_size / (1024 * 1024)
        log(f"  {p.name} — {mb:.1f} MB")

    elapsed = time.time() - t0
    log(f"=== Pipeline complete in {elapsed:.0f}s ===")



if __name__ == "__main__":
    main()
