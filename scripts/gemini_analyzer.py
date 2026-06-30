#!/usr/bin/env python3
"""
gemini_analyzer.py
──────────────────────────────────────────────────────────────────────────────
Gemini multi-modal video analyzer for the MrBeast pipeline.
Extracts the top 5 highest-retention clips (20-40s each) with structured
3-part voiceover scripts: HOOK → BODY → END.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Optional, List


def log(msg: str):
    print(msg, flush=True)


# ─── Master Prompt ─────────────────────────────────────────────────────────────

GEMINI_MASTER_PROMPT = """
You are an expert viral YouTube Shorts editor specialized in retention engineering for high-energy content like MrBeast and IShowSpeed videos.

Analyze this video and extract the top 5 moments BEST SUITED for highly viral YouTube Shorts.

CRITICAL CONSTRAINTS:
1. Every clip duration must be strictly between 20 seconds and 40 seconds maximum. Do not go under 20 seconds or over 40 seconds.
2. STRICT CLIP SEPARATION: You MUST select 5 completely distinct segments from the video. The timestamps for each clip must be at least 60 seconds apart from each other. Do NOT pull multiple clips from the exact same scene or timestamp. Space them out across the entire video.

For each clip, provide exact Start/End timestamps and write a SINGLE short AI hook.
- hook_script (0-5 seconds, max 15 words): A high-energy opener to instantly grab attention and stop the scroll (e.g. "Mr Beast is INSANE for this!", "Nobody saw this coming", or "OMG this is so insane").
- NEVER write "like and follow for part 2" or any closing remarks. The hook must instantly and naturally hand off to the original video's authentic audio which will play immediately after the hook.

You must return STRICTLY a raw JSON array with EXACTLY 5 objects. NO markdown, NO ```json fences, NO commentary — just the raw array:

[
  {
    "clip_number": 1,
    "start_time": "MM:SS",
    "end_time": "MM:SS",
    "duration_seconds": 30,
    "viral_title": "He survived 24 hours underground for THIS?!",
    "hook_script": "Nobody thought he would actually do this. But here we are."
  }
]

ABSOLUTE RULES:
1. Return EXACTLY 5 clips in the array.
2. duration_seconds for EVERY clip MUST be between 20 and 40.
3. start_time and end_time MUST be accurate real timestamps from the actual video content.
4. Write ALL numbers as spoken words in hook_script (e.g. 'twenty four' not '24') because this is fed to text-to-speech.
5. Identify moments with loud audio peaks, dramatic reactions, surprise reveals, challenge completions, or emotional climaxes.
6. Output ONLY the raw JSON array. Absolutely nothing else.
"""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def parse_mm_ss(ts: str) -> float:
    """Convert 'MM:SS' or 'HH:MM:SS' to float seconds."""
    ts = ts.strip()
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(ts)


def _clamp_clip(clip: dict) -> dict:
    """Enforce 20-40s duration on a single clip dict."""
    start = clip.get("start_sec", 30.0)
    end   = clip.get("end_sec", 60.0)
    dur   = end - start
    if dur < 20:
        end = start + 25  # extend to 25s minimum
        log(f"  ⚠ Clip {clip.get('clip_number','')} was {dur:.0f}s — extended to 25s.")
    elif dur > 40:
        end = start + 38  # trim to 38s
        log(f"  ⚠ Clip {clip.get('clip_number','')} was {dur:.0f}s — trimmed to 38s.")
    clip["end_sec"] = end
    clip["duration_seconds"] = end - start
    return clip


def _normalise_clip(raw: dict, idx: int) -> dict:
    """Parse timestamps and compute start_sec/end_sec."""
    start_sec = parse_mm_ss(raw.get("start_time", "0:30"))
    end_sec   = parse_mm_ss(raw.get("end_time", "1:00"))
    raw["start_sec"] = start_sec
    raw["end_sec"]   = end_sec
    raw["clip_number"] = raw.get("clip_number", idx + 1)

    # Ensure hook_script exists
    if not raw.get("hook_script"):
        raw["hook_script"] = "Wait, you are not ready for this."

    return _clamp_clip(raw)


# ─── Gemini analysis ──────────────────────────────────────────────────────────

def analyze_with_gemini(video_path: Path) -> Optional[List[dict]]:
    """
    Upload video to Gemini Files API and analyze with the master prompt.
    Returns a list of up to 5 clip dicts, or None on failure.
    """
    try:
        from google import genai
        from google.genai import types
        from google.api_core import exceptions as google_exceptions
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    from dotenv import load_dotenv
    load_dotenv(override=True)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    client = genai.Client(api_key=api_key)

    proxy_path = video_path.parent / "gemini_proxy.mp4"
    if not proxy_path.exists():
        log("  Creating a lightweight proxy video for faster Gemini processing...")
        import subprocess
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", "scale=-2:360", "-r", "15", "-b:v", "300k", "-b:a", "64k",
            str(proxy_path)
        ], capture_output=True)
        if proxy_path.exists():
            log("  ✅ Proxy created successfully.")
    
    upload_target = proxy_path if proxy_path.exists() else video_path

    MAX_RETRIES = 5
    BASE_WAIT   = 60

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"  Uploading video to Gemini Files API (attempt {attempt}/{MAX_RETRIES})...")
            video_file = client.files.upload(
                file=str(upload_target),
                config={"display_name": upload_target.name}
            )

            max_wait_time = 60  # 1 minute max wait
            wait_elapsed = 0
            while video_file.state == "PROCESSING":
                if wait_elapsed >= max_wait_time:
                    raise RuntimeError("Gemini processing timed out after 1 minute.")
                log("  ... video is processing, waiting 10s ...")
                time.sleep(10)
                wait_elapsed += 10
                video_file = client.files.get(name=video_file.name)

            if video_file.state == "FAILED":
                raise RuntimeError("Gemini processing failed.")

            log("  Video ready. Asking Gemini to find top 5 viral moments...")

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[video_file, GEMINI_MASTER_PROMPT],
                config=types.GenerateContentConfig(
                    temperature=0.35,
                    max_output_tokens=4096,
                )
            )

            raw_text = response.text.strip()
            log(f"  Gemini response received ({len(raw_text)} chars).")

            # Strip any accidental markdown
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text.strip())

            clips_raw = json.loads(raw_text)

            if not isinstance(clips_raw, list):
                clips_raw = [clips_raw]  # handle if Gemini returned a single object

            clips = [_normalise_clip(c, i) for i, c in enumerate(clips_raw)]

            log(f"  Gemini found {len(clips)} clip(s):")
            for c in clips:
                log(f"    #{c['clip_number']}: {c.get('start_time')} -> {c.get('end_time')} ({c['duration_seconds']:.0f}s) — {c.get('viral_title', 'N/A')}")

            return clips

        except Exception as e:
            from google.genai.errors import APIError
            if isinstance(e, APIError) and getattr(e, "code", 200) in [429, 500, 503]:
                wait = BASE_WAIT * attempt
                log(f"  Gemini rate limited/server error (attempt {attempt}/{MAX_RETRIES}). Retrying in {wait}s...")
                time.sleep(wait)
            else:
                log(f"  Gemini analysis failed: {e}")
                import traceback
                traceback.print_exc()
                break

    return None


# ─── Public entry point ───────────────────────────────────────────────────────

def get_all_clips(video_path: Path) -> List[dict]:
    """Main entry — returns top 5 clips via Gemini."""
    clips = analyze_with_gemini(video_path)
    if not clips:
        raise RuntimeError("Gemini analysis failed. PySceneDetect fallback has been disabled by user request.")
    return clips


# Keep a single-clip alias for backwards compatibility
def get_best_clip(video_path: Path) -> dict:
    """Returns only the #1 highest-retention clip."""
    return get_all_clips(video_path)[0]


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Usage: gemini_analyzer.py <video_path>")
        sys.exit(1)
    clips = get_all_clips(Path(sys.argv[1]))
    print(json.dumps(clips, indent=2))
