#!/usr/bin/env python3
"""
powerful_single_file_video_generator.py
====================================
A stronger Minecraft shader montage automation script inspired by the uploaded
reference video style: cinematic intro, glowing TOP 3 SHADERS title, fast
shader B-roll cuts, black fades, vignette, optional music/voiceover, and 60fps
export.

It does NOT copy copyrighted assets from the reference video. It recreates the
same editing language using your own clips, generated graphics, and your music.

Install:
  pip install moviepy pillow numpy yt-dlp edge-tts python-dotenv google-api-python-client google-auth

Generate with built-in reference-style plan:
  python3 video_generator.py \
    --action generate \
    --sources '["/path/to/source1.mp4", "https://youtube.com/watch?v=..."]' \
    --music scripts/music.mp3 \
    --output public/output/upload.mp4

Optional: you can still override the built-in plan:
  --edit-plan '{"title":"TOP 3\nSHADERS","sections":[...]}'

Upload:
  python3 video_generator.py --action upload --video public/output/upload.mp4 \
    --title "Top 3 Minecraft Shaders" --description "Links in bio"

Required env for upload only:
  YOUTUBE_CLIENT_ID=...
  YOUTUBE_CLIENT_SECRET=...
  YOUTUBE_REFRESH_TOKEN=...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        concatenate_audioclips,
        concatenate_videoclips,
    )
    import moviepy.video.fx as vfx
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "MoviePy import failed. Install with: pip install moviepy pillow numpy"
    ) from e

try:
    import yt_dlp  # type: ignore
except Exception:  # pragma: no cover
    yt_dlp = None

try:
    import edge_tts  # type: ignore
except Exception:  # pragma: no cover
    edge_tts = None

# Upload dependencies are imported only inside upload_to_youtube so generation
# works even if Google libraries are not installed.

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

TARGET_W = 480
TARGET_H = 854
TARGET_RATIO = TARGET_W / TARGET_H
TARGET_FPS = 30
DEFAULT_DURATION = 30.0

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_WORK_DIR = PROJECT_DIR / "public" / "output" / "video_work"
DEFAULT_OUTPUT = PROJECT_DIR / "public" / "output" / "upload.mp4"

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
]

# ──────────────────────────────────────────────────────────────────────────────
# Built-in edit plan
# ──────────────────────────────────────────────────────────────────────────────
# This makes the script a TRUE single-file automation.
# Run generation without --edit-plan and this default plan will be used.
# Change these names/timestamps directly inside this file whenever needed.

DEFAULT_EDIT_PLAN: Dict[str, Any] = {
    "title": "TOP 3\nSHADERS",
    "duration": 68.6,
    "intro_duration": 6.2,
    "music_volume": 0.68,
    "music_duck_factor": 0.35,
    "sections": [
        {
            "name": "Canva's Sunset Base",
            "corner_label": True,
            "clips": [
                {"source": 0, "timestamp": 6.5, "duration": 3.2},
                {"source": 0, "timestamp": 10.0, "duration": 4.2},
                {"source": 0, "timestamp": 14.5, "duration": 3.2},
                {"source": 0, "timestamp": 18.0, "duration": 5.6},
            ],
        },
        {
            "name": "Cinematic Night Shader",
            "corner_label": True,
            "clips": [
                {"source": 0, "timestamp": 23.0, "duration": 3.2},
                {"source": 0, "timestamp": 27.0, "duration": 4.2},
                {"source": 0, "timestamp": 31.0, "duration": 3.2},
                {"source": 0, "timestamp": 35.0, "duration": 5.6},
            ],
        },
        {
            "name": "Ultra Realistic Shader",
            "corner_label": True,
            "clips": [
                {"source": 0, "timestamp": 39.0, "duration": 3.2},
                {"source": 0, "timestamp": 43.0, "duration": 4.2},
                {"source": 0, "timestamp": 51.0, "duration": 3.2},
                {"source": 0, "timestamp": 55.0, "duration": 5.6},
            ],
        },
    ],
    "outro": {
        "text": "DOWNLOAD LINKS IN BIO",
        "duration": 7.4,
        "clips": [
            {"source": 0, "timestamp": 61.0, "duration": 7.4},
        ],
    },
    # Leave empty for music-only montage, or add dicts like:
    # {"start": 0, "text": "Stop playing Minecraft without these shaders."}
    "voiceovers": [],
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(f"[ref-style-editor] {msg}", flush=True)


def ensure_dir(path: Union[str, Path]) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for fp in FONT_CANDIDATES:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def parse_json_arg(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    if os.path.exists(value):
        with open(value, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON or missing file: {value}\n{e}") from e


def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def ffprobe_duration(path: Union[str, Path]) -> float:
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        return float(out)
    except Exception:
        return 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Source acquisition
# ──────────────────────────────────────────────────────────────────────────────

def download_source(url: str, out_path: Path) -> Path:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is required for YouTube URLs. Install: pip install yt-dlp")
    if out_path.exists():
        log(f"Using cached source video: {out_path}")
        return out_path
    log(f"Downloading source: {url}")
    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
        "outtmpl": str(out_path),
        "merge_output_format": "mp4",
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "quiet": False,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    if not out_path.exists():
        raise FileNotFoundError(f"Download failed: {url}")
    return out_path


def prepare_sources(sources: Sequence[str], work_dir: Path) -> List[Path]:
    import hashlib
    if not sources:
        raise ValueError("No sources provided. Pass --sources as JSON array of local mp4 paths or URLs.")
    prepared: List[Path] = []
    for i, src in enumerate(sources):
        src = str(src).strip()
        if is_url(src):
            url_hash = hashlib.md5(src.encode("utf-8")).hexdigest()
            prepared.append(download_source(src, work_dir / f"raw_{url_hash}.mp4"))
        else:
            p = Path(src).expanduser().resolve()
            if not p.exists():
                raise FileNotFoundError(f"Local source not found: {p}")
            prepared.append(p)
            log(f"Using local source[{i}]: {p}")
    return prepared


# ──────────────────────────────────────────────────────────────────────────────
# Frame / scene scoring for automatic clip picking
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SceneScore:
    source_index: int
    timestamp: float
    brightness: float
    contrast: float
    saturation: float
    warm: float
    dark: float
    score: float


def sample_frame_metrics(video_path: Path, source_index: int, step: float = 2.0) -> List[SceneScore]:
    """Cheap automatic scene scoring using ffmpeg-extracted frames via MoviePy.

    This is not AI vision. It is deterministic scoring that helps choose bright,
    saturated, cinematic shader moments when the edit plan has no timestamps.
    """
    scores: List[SceneScore] = []
    try:
        clip = VideoFileClip(str(video_path))
        duration = min(float(clip.duration), 900.0)  # keep scan lightweight
        times = np.arange(3.0, max(3.1, duration - 2.0), step)
        for t in times:
            try:
                frame = clip.get_frame(float(t))
                small = Image.fromarray(frame).resize((96, 54)).convert("RGB")
                arr = np.asarray(small).astype(np.float32) / 255.0
                r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
                brightness = float(arr.mean())
                contrast = float(arr.std())
                maxc = arr.max(axis=2)
                minc = arr.min(axis=2)
                saturation = float(np.mean((maxc - minc) / np.maximum(maxc, 1e-5)))
                warm = float(np.mean(np.maximum(r - b, 0)))
                dark = float(np.mean(arr < 0.12))
                # High score = colorful + contrast + not too dark + some warm glow.
                score = saturation * 1.8 + contrast * 1.2 + warm * 0.8 + brightness * 0.5 - dark * 0.35
                scores.append(SceneScore(source_index, float(t), brightness, contrast, saturation, warm, dark, score))
            except Exception:
                continue
        clip.close()
    except Exception as e:
        log(f"Scene scan failed for {video_path}: {e}")
    return scores


def auto_pick_moments(source_paths: Sequence[Path], count: int = 18) -> List[Dict[str, Any]]:
    all_scores: List[SceneScore] = []
    for i, p in enumerate(source_paths):
        all_scores.extend(sample_frame_metrics(p, i, step=2.0))

    if not all_scores:
        return [{"source": 0, "timestamp": 5 + i * 8} for i in range(count)]

    # Prevent picking many adjacent frames from the same scene.
    all_scores.sort(key=lambda s: s.score, reverse=True)
    picked: List[SceneScore] = []
    for s in all_scores:
        too_close = any(p.source_index == s.source_index and abs(p.timestamp - s.timestamp) < 8 for p in picked)
        if not too_close:
            picked.append(s)
        if len(picked) >= count:
            break

    picked.sort(key=lambda s: (s.source_index, s.timestamp))
    return [{"source": s.source_index, "timestamp": round(s.timestamp, 2)} for s in picked]


# ──────────────────────────────────────────────────────────────────────────────
# Video transforms and generated graphics
# ──────────────────────────────────────────────────────────────────────────────

def resize_crop_16x9(clip: VideoFileClip, w: int = TARGET_W, h: int = TARGET_H):
    cw, ch = clip.size
    ratio = cw / ch
    target = w / h
    if abs(ratio - target) < 0.015:
        return clip.resized((w, h))
    if ratio > target:
        new_h = h
        new_w = int(new_h * ratio)
        c = clip.resized((new_w, new_h))
        x1 = max(0, (new_w - w) // 2)
        return c.cropped(x1=x1, y1=0, x2=x1 + w, y2=h)
    new_w = w
    new_h = int(new_w / ratio)
    c = clip.resized((new_w, new_h))
    y1 = max(0, (new_h - h) // 2)
    return c.cropped(x1=0, y1=y1, x2=w, y2=y1 + h)


def subclip_exact(source: VideoFileClip, start: float, duration: float, fallback: float = 3.0):
    total = float(source.duration)
    if total <= 0:
        return ColorClip((TARGET_W, TARGET_H), color=(0, 0, 0)).with_duration(duration)
    start = max(0.0, min(float(start), max(0.0, total - 0.1)))
    if start + duration > total:
        start = max(0.0, total - duration - 0.05)
    end = min(total, start + duration)
    c = source.subclipped(start, end)
    if c.duration < duration - 0.05:
        # MoviePy will freeze the final frame when duration is extended.
        c = c.with_duration(duration)
    return resize_crop_16x9(c).with_duration(duration).with_fps(TARGET_FPS)


def make_vignette(duration: float, strength: int = 125) -> ImageClip:
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    px = img.load()
    cx, cy = TARGET_W / 2, TARGET_H / 2
    max_d = math.sqrt(cx * cx + cy * cy)
    for y in range(TARGET_H):
        for x in range(TARGET_W):
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2) / max_d
            alpha = int(max(0, min(strength, (d - 0.35) / 0.65 * strength)))
            px[x, y] = (0, 0, 0, alpha)
    return ImageClip(np.array(img)).with_duration(duration)


def make_black_flash(duration: float = 0.22):
    return ColorClip((TARGET_W, TARGET_H), color=(0, 0, 0)).with_duration(duration).with_fps(TARGET_FPS)


def generated_space_bg(seed: int = 7) -> Image.Image:
    random.seed(seed)
    img = Image.new("RGB", (TARGET_W, TARGET_H), (1, 3, 16))
    draw = ImageDraw.Draw(img, "RGBA")

    # Purple/blue nebula gradient bands.
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(2 + 12 * t)
        g = int(4 + 10 * t)
        b = int(18 + 42 * t)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b, 255))

    # Stars.
    for _ in range(1300):
        x = random.randint(0, TARGET_W - 1)
        y = random.randint(0, TARGET_H - 1)
        a = random.randint(60, 255)
        s = random.choice([1, 1, 1, 2])
        draw.ellipse([x, y, x + s, y + s], fill=(255, 255, 255, a))

    # Purple energy rings / Minecraft-like floating blocks.
    for i in range(5):
        x0 = random.randint(50, TARGET_W - 400)
        y0 = random.randint(60, TARGET_H - 420)
        w = random.randint(280, 560)
        h = random.randint(120, 270)
        draw.arc([x0, y0, x0 + w, y0 + h], start=10, end=330, fill=(156, 85, 255, 150), width=random.randint(8, 18))
        draw.arc([x0 + 10, y0 + 10, x0 + w - 10, y0 + h - 10], start=25, end=345, fill=(90, 185, 255, 70), width=4)

    for _ in range(22):
        x = random.randint(0, TARGET_W - 70)
        y = random.randint(0, TARGET_H - 70)
        s = random.randint(26, 70)
        angle = random.choice([0, 8, -8, 13, -13])
        block = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        bd = ImageDraw.Draw(block, "RGBA")
        bd.rounded_rectangle([0, 0, s, s], radius=10, outline=(130, 80, 255, 95), width=5, fill=(20, 15, 55, 60))
        block = block.rotate(angle, expand=True)
        img.paste(block, (x, y), block)

    # Add blur/glow.
    glow = img.filter(ImageFilter.GaussianBlur(1.2))
    return Image.blend(img, glow, 0.25)


def title_logo_png(title: str = "TOP 3\nSHADERS") -> Image.Image:
    """Generate a Minecraft-like icy stone title logo as transparent PNG."""
    W, H = 1150, 520
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    # Main stone plaque.
    plaque = [70, 80, W - 70, H - 70]
    draw.rounded_rectangle(plaque, radius=34, fill=(40, 53, 58, 235), outline=(105, 175, 190, 255), width=8)
    # Inner cracks / blocks.
    for i in range(18):
        x = random.randint(plaque[0] + 30, plaque[2] - 120)
        y = random.randint(plaque[1] + 20, plaque[3] - 60)
        bw = random.randint(60, 160)
        bh = random.randint(22, 70)
        draw.rectangle([x, y, x + bw, y + bh], outline=(0, 0, 0, 55), width=3)

    # Cyan crystals.
    for x, y, s in [(120, 45, 70), (970, 45, 75), (160, 405, 55), (930, 410, 58)]:
        pts = [(x, y), (x + s // 2, y - s), (x + s, y), (x + s // 2, y + s // 2)]
        draw.polygon(pts, fill=(35, 235, 255, 210), outline=(190, 255, 255, 240))

    lines = title.upper().split("\\n") if "\\n" in title else title.upper().split("\n")
    if len(lines) == 1:
        lines = [lines[0]]
    font_size = 162 if len(lines) >= 2 else 205
    font = load_font(font_size)
    y = 126 if len(lines) >= 2 else 180
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=7)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        # Heavy black/stone outline.
        draw.text((x + 8, y + 8), line, font=font, fill=(0, 0, 0, 170), stroke_width=12, stroke_fill=(0, 0, 0, 230))
        # Cyan glow strokes.
        draw.text((x, y), line, font=font, fill=(85, 235, 255, 255), stroke_width=7, stroke_fill=(10, 45, 65, 255))
        # White top highlight.
        draw.text((x, y - 7), line, font=font, fill=(225, 255, 255, 180), stroke_width=1, stroke_fill=(225, 255, 255, 60))
        y += 158

    # Outer glow.
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    glow.alpha_composite(img)
    alpha = glow.getchannel("A").filter(ImageFilter.GaussianBlur(18))
    glow_col = Image.new("RGBA", img.size, (0, 220, 255, 85))
    glow_col.putalpha(alpha)
    out = Image.alpha_composite(glow_col, img)
    return out


def creeper_icon_png(size: int = 112) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([4, 4, size - 4, size - 4], radius=18, fill=(255, 182, 31, 255), outline=(46, 26, 0, 230), width=6)
    eye = size // 4
    d.rectangle([eye, eye, eye + size // 6, eye + size // 6], fill=(35, 25, 15, 255))
    d.rectangle([size - eye - size // 6, eye, size - eye, eye + size // 6], fill=(35, 25, 15, 255))
    d.rectangle([size // 2 - size // 12, size // 2 - size // 16, size // 2 + size // 12, size // 2 + size // 5], fill=(35, 25, 15, 255))
    d.rectangle([size // 2 - size // 4, size // 2 + size // 8, size // 2 - size // 12, size // 2 + size // 3], fill=(35, 25, 15, 255))
    d.rectangle([size // 2 + size // 12, size // 2 + size // 8, size // 2 + size // 4, size // 2 + size // 3], fill=(35, 25, 15, 255))
    return img


def make_intro(title: str, duration: float = 6.2, work_dir: Optional[Path] = None):
    work_dir = ensure_dir(work_dir or DEFAULT_WORK_DIR)
    bg_path = work_dir / "generated_space_intro.png"
    logo_path = work_dir / "generated_top3_logo.png"
    icon_path = work_dir / "generated_creeper_icon.png"

    generated_space_bg().save(bg_path)
    title_logo_png(title).save(logo_path)
    creeper_icon_png().save(icon_path)

    bg = ImageClip(str(bg_path)).with_duration(duration).with_fps(TARGET_FPS)
    # Subtle push-in for intro background.
    try:
        bg = bg.resized(lambda t: 1.0 + 0.025 * min(max(t / duration, 0), 1)).cropped(
            x1=0, y1=0, x2=TARGET_W, y2=TARGET_H
        )
    except Exception:
        pass

    # Resize logo to fit vertical screen width
    logo_w = TARGET_W - 60
    logo = (
        ImageClip(str(logo_path))
        .resized(width=logo_w)
        .with_duration(duration - 1.05)
        .with_start(1.05)
        .with_position(("center", "center"))
    )

    # Two small icons like the reference video lower corners.
    icon_w = 48 if TARGET_W < 600 else 112
    icon1 = ImageClip(str(icon_path)).resized(width=icon_w).with_duration(duration).with_position((TARGET_W - icon_w - 20, TARGET_H - icon_w - 60))
    icon2 = ImageClip(str(icon_path)).resized(width=icon_w).with_duration(duration).with_position((20, TARGET_H - icon_w - 60))

    # White comet sweep that reveals the logo.
    comet = Image.new("RGBA", (700, 220), (0, 0, 0, 0))
    cd = ImageDraw.Draw(comet, "RGBA")
    for i in range(26):
        alpha = int(255 * (1 - i / 26))
        cd.line([(80 + i * 9, 160 - i * 4), (600 + i * 4, 30 + i)], fill=(255, 235, 165, alpha), width=max(1, 16 - i // 2))
    comet = comet.filter(ImageFilter.GaussianBlur(1.2))
    comet_path = work_dir / "generated_comet.png"
    comet.save(comet_path)
    comet_clip = (
        ImageClip(str(comet_path))
        .with_duration(1.35)
        .with_start(0.75)
        .with_position(lambda t: (max(-699, min(int(-650 + (TARGET_W + 900) * min(max(t / 1.35, 0), 1)), TARGET_W - 1)), 160))
    )

    black_start = ColorClip((TARGET_W, TARGET_H), color=(0, 0, 0)).with_duration(0.22).with_start(0)
    vignette = make_vignette(duration, strength=100)
    comp = CompositeVideoClip([bg, logo, icon1, icon2, comet_clip, vignette, black_start]).with_duration(duration)
    return comp.with_fps(TARGET_FPS)


def make_label_overlay(text: str, duration: float, pos: Tuple[str, int] = ("center", 120), small: bool = False) -> ImageClip:
    text = str(text).upper()
    h = 80 if not small else 54
    if TARGET_W >= 600:
        h = 104 if not small else 72
        
    img = Image.new("RGBA", (TARGET_W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    
    font_size = 64 if not small else 42
    if TARGET_W < 600:
        font_size = 32 if not small else 24
        
    font = load_font(font_size)
    bbox = d.textbbox((0, 0), text, font=font, stroke_width=3)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (TARGET_W - tw) // 2
    y = (h - th) // 2 - 4
    
    pad_x = 20 if TARGET_W < 600 else 34
    pad_y = 10 if TARGET_W < 600 else 18
    d.rounded_rectangle([x - pad_x, y - pad_y, x + tw + pad_x, y + th + pad_y], radius=12 if TARGET_W < 600 else 18, fill=(0, 0, 0, 170), outline=(65, 225, 255, 230), width=2 if TARGET_W < 600 else 3)
    d.text((x, y), text, font=font, fill=(230, 255, 255, 255), stroke_width=2 if TARGET_W < 600 else 3, stroke_fill=(0, 26, 36, 255))
    
    # Vertically positioned lower in Shorts
    final_pos = pos
    if TARGET_W < 600 and pos == ("center", 58):
        final_pos = ("center", 120)
        
    return ImageClip(np.array(img)).with_duration(duration).with_position(final_pos)


def make_corner_source_label(text: str, duration: float) -> ImageClip:
    """Small top-right shader-name box similar to in-game overlay clips."""
    text = str(text)
    font_size = 18 if TARGET_W < 600 else 28
    font = load_font(font_size)
    pad = 10 if TARGET_W < 600 else 16
    
    temp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d0 = ImageDraw.Draw(temp)
    bbox = d0.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    img_w = tw + pad * 2 + (30 if TARGET_W < 600 else 56)
    img_h = th + pad * 2
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=6, fill=(0, 0, 0, 165), outline=(255, 255, 255, 65), width=1)
    
    icon_sz = 18 if TARGET_W < 600 else 36
    d.rectangle([pad, pad, pad + icon_sz, pad + icon_sz], fill=(128, 35, 24, 255), outline=(255, 135, 80, 180), width=1 if TARGET_W < 600 else 2)
    d.text((pad + icon_sz + 12, pad - 2), text, font=font, fill=(255, 255, 255, 240))
    return ImageClip(np.array(img)).with_duration(duration).with_position((TARGET_W - img.width - 16 if TARGET_W < 600 else TARGET_W - img.width - 28, 20))


def make_caption_clip(text: str, duration: float) -> ImageClip:
    text = str(text).upper()
    font_size = 36 if TARGET_W < 600 else 72
    font = load_font(font_size)
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    
    lines = []
    words = text.split()
    current_line = []
    for w in words:
        current_line.append(w)
        bbox = d.textbbox((0, 0), " ".join(current_line), font=font)
        if bbox[2] - bbox[0] > TARGET_W - 80:
            current_line.pop()
            lines.append(" ".join(current_line))
            current_line = [w]
    if current_line:
        lines.append(" ".join(current_line))
        
    y = TARGET_H - 340 if TARGET_W < 600 else TARGET_H - 240
    for line in lines:
        bbox = d.textbbox((0, 0), line, font=font, stroke_width=6)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (TARGET_W - tw) // 2
        
        # Draw background stroke/shadow
        d.text((x + 6, y + 6), line, font=font, fill=(0, 0, 0, 200), stroke_width=10, stroke_fill=(0, 0, 0, 255))
        # Draw main bright yellow text (Minecraft style)
        d.text((x, y), line, font=font, fill=(255, 230, 80, 255), stroke_width=4, stroke_fill=(60, 40, 0, 255))
        y += th + 15
        
    return ImageClip(np.array(img)).with_duration(duration).with_position(("center", "center"))


def build_segment(
    source_clips: Sequence[VideoFileClip],
    clip_info: Dict[str, Any],
    default_duration: float,
    label: Optional[str] = None,
    show_corner_label: bool = True,
):
    idx = int(clip_info.get("source", clip_info.get("video_index", 0)))
    idx = max(0, min(idx, len(source_clips) - 1))
    start = safe_float(clip_info.get("timestamp", clip_info.get("start", 3.0)), 3.0)
    dur = safe_float(clip_info.get("duration", default_duration), default_duration)
    c = subclip_exact(source_clips[idx], start, dur)

    layers: List[Any] = [c]
    if show_corner_label and label:
        layers.append(make_corner_source_label(label, dur))
    if clip_info.get("big_label"):
        layers.append(make_label_overlay(str(clip_info["big_label"]), dur, small=False))
    layers.append(make_vignette(dur, strength=70))
    return CompositeVideoClip(layers).with_duration(dur).with_fps(TARGET_FPS)


def normalize_plan(edit_plan: Dict[str, Any], auto_moments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Support both the new plan format and your older shader1/shader2/shader3 format."""
    if "sections" in edit_plan:
        return edit_plan

    # Convert old script style into reference-style sections.
    sections = []
    moment_i = 0
    for key, default_name in [("shader1", "Shader 1"), ("shader2", "Shader 2"), ("shader3", "Shader 3")]:
        s = edit_plan.get(key, {}) or {}
        name = s.get("name") or s.get("label") or default_name
        refs = []
        for old_key, dur in [
            ("vanilla_start_1", 3.1),
            ("shader_start_1", 4.2),
            ("vanilla_start_2", 3.1),
            ("shader_start_2", 5.6),
        ]:
            ref = s.get(old_key)
            if ref is None:
                ref = auto_moments[moment_i % len(auto_moments)]
                moment_i += 1
            if isinstance(ref, (int, float)):
                ref = {"source": 0, "timestamp": ref}
            if isinstance(ref, dict):
                ref = dict(ref)
                ref["duration"] = ref.get("duration", dur)
                refs.append(ref)
        sections.append({"name": name, "clips": refs})

    return {
        "title": edit_plan.get("title", "TOP 3\\nSHADERS"),
        "intro_duration": 6.2,
        "sections": sections,
        "outro": edit_plan.get("outro", {"text": "DOWNLOAD LINKS IN BIO", "duration": 7.4}),
        "voiceovers": edit_plan.get("voiceovers", []),
    }


def _sanitize_pairs(raw: Any, num_pairs: int) -> List[Dict[str, Any]]:
    """Coerce Gemini's JSON output into a safe, well-typed list of pairs.

    Gemini occasionally returns timestamps as strings, omits a field, or
    returns fewer/more pairs than asked for. This normalizes all of that so
    downstream code can rely on float vanilla_start/shader_start and a
    string shader_name.
    """
    cleaned: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            cleaned.append({
                "shader_name": str(item.get("shader_name") or f"Shader Pack {i + 1}").strip() or f"Shader Pack {i + 1}",
                "vanilla_start": safe_float(item.get("vanilla_start"), 10.0 + i * 40),
                "shader_start": safe_float(item.get("shader_start"), 30.0 + i * 40),
            })
    if not cleaned:
        cleaned = [
            {"shader_name": f"Shader Pack {i + 1}", "vanilla_start": 10.0 + i * 40, "shader_start": 30.0 + i * 40}
            for i in range(num_pairs)
        ]
    # Pad or trim to exactly num_pairs so the timeline math stays predictable.
    while len(cleaned) < num_pairs:
        i = len(cleaned)
        cleaned.append({"shader_name": f"Shader Pack {i + 1}", "vanilla_start": 10.0 + i * 40, "shader_start": 30.0 + i * 40})
    return cleaned[:num_pairs]


def get_gemini_pairs(video_path: Path, num_pairs: int) -> List[Dict[str, float]]:
    # This function is rewritten to be more robust against common auth issues.
    # It uses the official Python SDK and handles rate limiting with retries.
    try:
        import google.generativeai as google_genai
        from google.api_core import exceptions as google_exceptions
    except ImportError:
        raise RuntimeError("Google GenAI SDK not found. Please run: pip install google-generativeai")

    import time
    import os
    import json

    log("▶ Analysing video with Gemini API …")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    # The `ACCESS_TOKEN_TYPE_UNSUPPORTED` error often happens when the SDK
    # mistakenly tries to use Vertex AI authentication with a standard Gemini
    # API key. We explicitly disable it to be safe.
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true":
        log("  [INFO] GOOGLE_GENAI_USE_VERTEXAI is set. Forcing 'false' to use API key auth.")
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"

    google_genai.configure(api_key=api_key.strip())

    MAX_RETRIES = 5
    BASE_WAIT   = 60  # seconds to wait on first 429

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"  Uploading video to Gemini Files API (attempt {attempt}/{MAX_RETRIES})…")
            video_file = google_genai.upload_file(
                path=video_path,
                display_name=video_path.name
            )

            while video_file.state.name == "PROCESSING":
                log("  … video is processing, waiting 10s …")
                time.sleep(10)
                video_file = google_genai.get_file(name=video_file.name)

            if video_file.state.name == "FAILED":
                raise RuntimeError(f"Gemini video processing FAILED. Full details: {video_file.error}")

            log("  Video ready. Asking Gemini for timestamps …")
            prompt = f"""
            You are a professional YouTube Shorts video editor. Watch this Minecraft shader comparison video carefully.
            Your task is to find exactly {num_pairs} pairs of timestamps showing the BEST before/after shader contrast.
            For each pair, also identify the NAME of the shader pack being shown (e.g. "BSL Shaders", "Complementary Shaders", etc.).
            - "vanilla_start" is the start of a clearly VANILLA (no shader) moment.
            - "shader_start" is the start of a clearly SHADERS-ON moment.
            - Space the pairs out. Do NOT cluster them all at the start.
            Return ONLY a valid JSON array, no other text. Format:
            [{{"shader_name": "...", "vanilla_start": 0.0, "shader_start": 0.0}}]
            """
            model = google_genai.GenerativeModel(model_name="gemini-1.5-flash")
            response = model.generate_content(
                [video_file, prompt],
                generation_config=google_genai.types.GenerationConfig(
                    response_mime_type="application/json"
                ),
            )
            # The SDK now automatically parses JSON responses
            raw_pairs = response.text
            pairs = _sanitize_pairs(json.loads(raw_pairs), num_pairs)
            log(f"  Gemini returned {len(pairs)} usable pair(s)")
            return pairs
        except (google_exceptions.ResourceExhausted, google_exceptions.InternalServerError) as e:
            err_str = str(e)
            wait_secs = BASE_WAIT * attempt
            log(f"  ⚠ Gemini API busy (attempt {attempt}/{MAX_RETRIES}). Waiting {wait_secs}s before retry…")
            time.sleep(wait_secs)
        except Exception as e:
            log(f"  ❌ An unexpected error occurred with the Gemini API: {e}")
            log("     Switching to fallback timestamps.")
            break # Exit retry loop on unexpected errors

    log("  Using fallback timestamps.")
    return [{"shader_name": f"Shader Pack {i + 1}", "vanilla_start": 10.0 + i*40, "shader_start": 30.0 + i*40} for i in range(num_pairs)]

def build_reference_style_video(source_paths: Sequence[Path], edit_plan: Dict[str, Any], music_path: Optional[Path], output: Path, work_dir: Path) -> Path:
    ensure_dir(work_dir)
    ensure_dir(output.parent)

    if not source_paths:
        raise ValueError("No source videos provided.")

    log("Loading source video...")
    raw_path = source_paths[0]
    raw_clip = VideoFileClip(str(raw_path))

    # Ask Gemini to find exactly 3 shader pairs with names
    pairs = get_gemini_pairs(raw_path, 3)

    # 3 pairs x (before + after) x 5.0s = 30s, matching the requested ~30s short.
    CLIP_DURATION = 5.0  # BEFORE + AFTER per pair

    # ── Build voiceover script timed to the actual clip structure ────────────
    # Layout: [BEFORE_1 5.0s][AFTER_1 5.0s][BEFORE_2 5.0s][AFTER_2 5.0s][BEFORE_3 5.0s][AFTER_3 5.0s]
    # Total = 30 seconds
    pair_lines = []
    for i, p in enumerate(pairs):
        name = p.get("shader_name", f"this shader pack")
        if i == 0:
            pair_lines.append(
                f"First up, we have {name}. "
                f"Watch how it transforms the world with incredible lighting and vibrant colors."
            )
        elif i == 1:
            pair_lines.append(
                f"Next, let's check out {name}. "
                f"This one adds stunning water reflections and realistic shadows. It's a game-changer."
            )
        else:
            pair_lines.append(
                f"And for our final shader, this is {name}. "
                f"The god rays and atmospheric fog are just breathtaking. You have to try this one."
            )

    # Each pair = 10s -> 3 pairs = 30s total.
    # Voiceover lines are spread roughly across the matching pair's window.
    VOICEOVER_SCRIPT = "  ".join(pair_lines)
    log(f"  Voiceover script: {VOICEOVER_SCRIPT[:80]}…")

    # ── Assemble alternating BEFORE/AFTER clips ───────────────────────────────
    log("Assembling alternating video clips...")
    segments = []
    for p in pairs:
        v_start = float(p.get("vanilla_start", 0.0))
        s_start = float(p.get("shader_start", 0.0))
        shader_name = p.get("shader_name", "Shader Pack")

        # ─ BEFORE clip ─
        v_clip  = subclip_exact(raw_clip, v_start, CLIP_DURATION)
        v_label = make_label_overlay("⬛  BEFORE", CLIP_DURATION, pos=("center", 80))
        segments.append(
            CompositeVideoClip([v_clip, v_label]).with_duration(CLIP_DURATION)
        )

        # ─ AFTER clip  ─
        s_clip  = subclip_exact(raw_clip, s_start, CLIP_DURATION)
        s_label = make_label_overlay(f"✨  AFTER  |  {shader_name}", CLIP_DURATION, pos=("center", 80))
        segments.append(
            CompositeVideoClip([s_clip, s_label]).with_duration(CLIP_DURATION)
        )

    full = concatenate_videoclips(segments, method="compose").with_fps(TARGET_FPS)
    total_duration = full.duration
    log(f"  Video assembled: {total_duration:.1f}s")

    # ── Audio: TTS voiceover + background music ───────────────────────────────
    plan = {
        "voiceover_script": VOICEOVER_SCRIPT,
        "music_volume":      0.55,
        "music_duck_factor": 0.20,
    }

    # Generate the voiceover first so we know its real duration. If it runs
    # a touch longer than the assembled clips (e.g. long shader names), we
    # freeze the final frame instead of cutting the voice off mid-sentence.
    vtt_path = work_dir / "voiceover.vtt"
    vo_clip = None
    if plan["voiceover_script"].strip():
        # generate_tts now has its own robust error handling and logging
        vo_clip = generate_tts(plan["voiceover_script"], work_dir / "voice.mp3", "en-US-ChristopherNeural", "+12%", vtt_path)
    else:
        log("  No voiceover script. Skipping TTS generation.")

    if vo_clip is not None and vo_clip.duration > total_duration:
        extra = vo_clip.duration - total_duration
        log(f"  Voiceover ({vo_clip.duration:.1f}s) is longer than the video ({total_duration:.1f}s); "
            f"extending final frame by {extra:.1f}s so the voice isn't cut off.")
        # Hold the last segment's final frame for the extra time.
        last_frame_hold = segments[-1].with_duration(segments[-1].duration + extra)
        segments[-1] = last_frame_hold
        full = concatenate_videoclips(segments, method="compose").with_fps(TARGET_FPS)
        total_duration = full.duration

    audio_tracks = []
    if vo_clip is not None:
        audio_tracks.append(vo_clip.with_start(0))
    audio = build_audio(plan, work_dir, music_path, total_duration, precomputed_voice=audio_tracks)
    if audio is not None:
        full = full.with_audio(audio)

    # ── Captions from VTT (word-level, perfectly synced by edge-tts) ─────────
    captions = parse_vtt(vtt_path)
    if captions:
        log(f"  Applying {len(captions)} caption cue(s)…")
        caption_clips = [full]
        for cap in captions:
            start = cap["start"]
            end   = min(cap["end"], total_duration)
            if start < total_duration and end > start:
                c_clip = make_caption_clip(cap["text"], end - start).with_start(start)
                caption_clips.append(c_clip)
        if len(caption_clips) > 1:
            full = CompositeVideoClip(caption_clips).with_duration(total_duration).with_fps(TARGET_FPS)
    else:
        log("  No VTT captions found — voiceover audio only.")

    log(f"Writing final video: {output}")
    full.write_videofile(
        str(output),
        fps=TARGET_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        threads=4,
        logger="bar",
    )
    log(f"DONE: {output}")
    raw_clip.close()
    return output


def make_outro_card(text: str, duration: float, work_dir: Path):
    # The reference ends with a final cinematic/backrooms-style clip. This card is
    # used only when you do not provide an outro clip.
    W, H = TARGET_W, TARGET_H
    img = Image.new("RGB", (W, H), (12, 9, 5))
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(H):
        t = y / H
        col = (int(18 + 90 * t), int(14 + 58 * t), int(8 + 16 * t))
        d.line([(0, y), (W, y)], fill=col)
    # Backrooms-ish ceiling rectangles.
    for x in range(80, W, 250):
        d.rounded_rectangle([x, 70, x + 140, 130], radius=8, fill=(255, 236, 166, 160))
    for x in range(-120, W, 300):
        d.rectangle([x, 260, x + 190, H], fill=(155, 115, 42, 65))
    font_big = load_font(92)
    font_small = load_font(46)
    bbox = d.textbbox((0, 0), text.upper(), font=font_big, stroke_width=6)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((W - tw) // 2, 430), text.upper(), font=font_big, fill=(255, 246, 208, 255), stroke_width=6, stroke_fill=(35, 20, 2, 255))
    sub = "FULL DOWNLOAD LINKS IN DESCRIPTION"
    b2 = d.textbbox((0, 0), sub, font=font_small)
    d.text(((W - (b2[2]-b2[0])) // 2, 555), sub, font=font_small, fill=(255, 226, 150, 210))
    path = work_dir / "generated_outro_card.png"
    img.save(path)
    return CompositeVideoClip([ImageClip(str(path)).with_duration(duration), make_vignette(duration, strength=95)]).with_duration(duration).with_fps(TARGET_FPS)


# ──────────────────────────────────────────────────────────────────────────────
# Audio: music, optional TTS, ducking
# ──────────────────────────────────────────────────────────────────────────────

async def _tts_save(text: str, out_path: Path, voice: str, rate: str, vtt_path: Optional[Path] = None) -> None:
    if edge_tts is None:
        raise RuntimeError("edge-tts is not installed. Install: pip install edge-tts")
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    
    if vtt_path:
        # Edge TTS saves the audio and optionally creates subtitles using the submaker
        submaker = edge_tts.SubMaker()
        with open(out_path, "wb") as file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.create_sub((chunk["offset"], chunk["duration"]), chunk["text"])
        with open(vtt_path, "w", encoding="utf-8") as file:
            file.write(str(submaker))
    else:
        await communicate.save(str(out_path))


def generate_tts(text: str, out_path: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+8%", vtt_path: Optional[Path] = None) -> Optional[AudioFileClip]:
    if not text:
        log("  TTS skipped: no text provided.")
        return None
    log(f"  Generating TTS audio to {out_path}...")
    try:
        asyncio.run(_tts_save(text, out_path, voice, rate, vtt_path))
        if not out_path.exists() or out_path.stat().st_size < 1024:
            log(f"  ❌ TTS generation failed: output file is missing or empty ({out_path})")
            return None
        log(f"  TTS audio generated successfully.")
        return AudioFileClip(str(out_path))
    except Exception as e:
        log(f"  ❌ TTS generation failed with an exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def parse_vtt(vtt_path: Path) -> List[Dict[str, Any]]:
    captions = []
    if not vtt_path.exists():
        return captions
    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    blocks = content.strip().split("\n\n")
    for block in blocks:
        lines = block.split("\n")
        if len(lines) >= 2 and "-->" in lines[1]:
            time_line = lines[1]
            text = " ".join(lines[2:])
        elif len(lines) >= 1 and "-->" in lines[0]:
            time_line = lines[0]
            text = " ".join(lines[1:])
        else:
            continue
            
        parts = time_line.split("-->")
        if len(parts) != 2:
            continue
            
        def parse_time(t_str):
            t_str = t_str.strip().replace(",", ".")
            parts = t_str.split(":")
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
            elif len(parts) == 2:
                m, s = parts
                return int(m) * 60 + float(s)
            return float(t_str)

        start = parse_time(parts[0])
        end = parse_time(parts[1])
        if text.strip():
            captions.append({"start": start, "end": end, "text": text.strip()})
    return captions


def build_audio(plan: Dict[str, Any], work_dir: Path, music_path: Optional[Path], total_duration: float, precomputed_voice: Optional[List[Any]] = None):
    log("▶ Building final audio track...")
    tracks: List[Any] = []
    vo_intervals: List[Tuple[float, float]] = []
    vtt_path = work_dir / "voiceover.vtt"

    if precomputed_voice:
        log(f"  Adding {len(precomputed_voice)} pre-computed voice track(s).")
        for clip in precomputed_voice:
            tracks.append(clip)
            vo_intervals.append((float(clip.start or 0.0), float(clip.start or 0.0) + clip.duration))
    elif "voiceover_script" in plan:
        text = str(plan["voiceover_script"]).strip()
        if text:
            try:
                clip = generate_tts(text, work_dir / "voice.mp3", "en-US-ChristopherNeural", "+12%", vtt_path)
                if clip:
                    # Let the voiceover start immediately
                    start = 0.0
                    tracks.append(clip.with_start(start))
                    vo_intervals.append((start, start + clip.duration))
            except Exception as e:
                log(f"Voiceover skipped: {e}")
    else:
        # Fallback to old format
        voiceovers = plan.get("voiceovers", [])
        if isinstance(voiceovers, dict):
            voiceovers = list(voiceovers.values())
        for i, vo in enumerate(voiceovers or []):
            if not isinstance(vo, dict):
                continue
            text = str(vo.get("text", "")).strip()
            if not text:
                continue
            start = safe_float(vo.get("start", 0), 0)
            try:
                clip = generate_tts(text, work_dir / f"voice_{i}.mp3", vo.get("voice", "en-US-ChristopherNeural"), vo.get("rate", "+8%"))
                if clip:
                    tracks.append(clip.with_start(start))
                    vo_intervals.append((start, start + clip.duration))
            except Exception as e:
                log(f"Voiceover skipped: {e}")

    # Music is the heart of this reference style. Put your intense/cinematic song
    # in --music. If no music is present and no voiceover exists, output is silent.
    if music_path and music_path.exists():
        log(f"  Adding background music from: {music_path}")
        music = AudioFileClip(str(music_path))
        if music.duration < total_duration:
            loops = int(total_duration / music.duration) + 2
            music = concatenate_audioclips([music] * loops)
        music = music.subclipped(0, total_duration)
        duck = float(plan.get("music_duck_factor", 0.35))
        base_vol = float(plan.get("music_volume", 0.65))
        if vo_intervals:
            # Duck music during voiceover.
            points = sorted(set([0.0, total_duration] + [t for interval in vo_intervals for t in interval]))
            music_parts = []
            for a, b in zip(points, points[1:]):
                if b <= a:
                    continue
                is_ducked = any(a >= s and b <= e for s, e in vo_intervals)
                vol = base_vol * (duck if is_ducked else 1.0)
                music_parts.append(music.subclipped(a, b).with_volume_scaled(vol))
            if music_parts:
                tracks.insert(0, concatenate_audioclips(music_parts).with_start(0))
        else:
            tracks.insert(0, music.with_volume_scaled(base_vol).with_start(0))
    else:
        log("  No music file found or provided. Add --music for background audio.")

    if not tracks:
        log("  No audio tracks to composite. Video will be silent.")
        return None

    log(f"  Compositing {len(tracks)} audio track(s).")
    return CompositeAudioClip(tracks).with_duration(total_duration)


# ──────────────────────────────────────────────────────────────────────────────
# YouTube Upload with env-only secrets
# ──────────────────────────────────────────────────────────────────────────────

def upload_to_youtube(video_path: Path, title: str, description: str, privacy: str = "public") -> None:
    import sys
    from dotenv import load_dotenv
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.auth.exceptions import RefreshError

    load_dotenv()
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    if not client_id or not client_secret or not refresh_token:
        raise RuntimeError("Missing YouTube env vars. Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN.")

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        youtube = build("youtube", "v3", credentials=creds)
        body = {
            "snippet": {"title": title, "description": description, "categoryId": "20"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = request.execute()
        log(f"Upload complete: https://youtu.be/{response.get('id')}")
    except RefreshError:
        error_message = """
YouTube Authentication Error: The YOUTUBE_REFRESH_TOKEN is invalid or expired.
This is a common issue, especially for apps in 'Testing' mode where tokens expire after 7 days.
To fix this, you must generate a NEW refresh token and update the YOUTUBE_REFRESH_TOKEN value in your .env file. Please refer to the README for instructions.
"""
        print(error_message, file=sys.stderr, flush=True)
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Reference-style Minecraft shader video automation")
    parser.add_argument("--action", required=True, choices=["generate", "upload"])
    parser.add_argument("--sources", help="JSON array of local source videos or YouTube URLs")
    parser.add_argument("--url", help="Single local video path or YouTube URL, legacy shortcut")
    parser.add_argument("--edit-plan", dest="edit_plan", help="Optional JSON string or path to JSON edit plan. If omitted, built-in DEFAULT_EDIT_PLAN is used.")
    parser.add_argument("--music", help="Path to music.mp3")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Final output mp4")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR), help="Temporary work directory")
    parser.add_argument("--video", help="Video path for upload action")
    parser.add_argument("--title", help="YouTube upload title")
    parser.add_argument("--description", help="YouTube upload description")
    parser.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    args = parser.parse_args()

    try:
        if args.action == "generate":
            # Single-file default: no separate edit-plan JSON needed.
            if args.sources:
                sources = parse_json_arg(args.sources, [])
            elif args.url:
                sources = [args.url]
            else:
                sources = []

            if isinstance(sources, str):
                sources = [sources]

            edit_plan = parse_json_arg(args.edit_plan, DEFAULT_EDIT_PLAN.copy()) if args.edit_plan else DEFAULT_EDIT_PLAN.copy()
            work_dir = ensure_dir(args.work_dir)
            source_paths = prepare_sources(sources, work_dir)
            music_path = Path(args.music).expanduser().resolve() if args.music else None
            build_reference_style_video(source_paths, edit_plan, music_path, Path(args.output).expanduser().resolve(), work_dir)
        else:
            video = Path(args.video or args.output).expanduser().resolve()
            if not video.exists():
                raise FileNotFoundError(f"Video not found: {video}")
            if not args.title or not args.description:
                raise ValueError("--title and --description are required for upload.")
            upload_to_youtube(video, args.title, args.description, args.privacy)
    except Exception:
        print("\n[FATAL ERROR]")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
