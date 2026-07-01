#!/usr/bin/env python3
"""
auto_scheduler.py
─────────────────────────────────────────────────────────────────────────────
Background automation engine for the YouTube Shorts pipeline.

Runs forever, waking up every 60 seconds to check if any channel is due for:
  • Minecraft  → generate 1 short → upload to Minecraft channel
  • MrBeast   → if clip queue has unused clips → upload next one
                else → generate 5 clips → queue them → upload the first

Usage:
    python3 scripts/auto_scheduler.py
    python3 scripts/auto_scheduler.py --test  (one-shot dry run)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_DIR  = SCRIPT_DIR.parent
STATE_PATH   = PROJECT_DIR / "scheduler_state.json"
OUTPUT_DIR   = PROJECT_DIR / "public" / "output"
LOG_PATH     = PROJECT_DIR / "scheduler.log"

INTERVAL_SECONDS = 60  # how often to check


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"⚠ Could not read state: {e}")
        return {}


def write_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_due(next_run_iso: str | None) -> bool:
    if not next_run_iso:
        return False
    try:
        next_run = datetime.fromisoformat(next_run_iso)
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= next_run
    except Exception:
        return False


def pick_next_url(channel_state: dict) -> str | None:
    """Return next unused URL. If all used, cycle them back."""
    urls = channel_state.get("urls", [])
    if not urls:
        # All used — cycle back
        used = channel_state.get("used_urls", [])
        if used:
            log("  All URLs used — cycling back to beginning.")
            channel_state["urls"] = used[:]
            channel_state["used_urls"] = []
            urls = channel_state["urls"]
        else:
            log("  ❌ No URLs in library. Add source URLs first.")
            return None
    return urls[0]


def mark_url_used(channel_state: dict, url: str):
    urls = channel_state.get("urls", [])
    if url in urls:
        urls.remove(url)
    channel_state["urls"] = urls
    used = channel_state.get("used_urls", [])
    if url not in used:
        used.append(url)
    channel_state["used_urls"] = used


def schedule_next_run(channel_state: dict):
    hours = channel_state.get("interval_hours", 5)
    channel_state["next_run"] = (
        datetime.now(timezone.utc) + timedelta(hours=hours)
    ).isoformat()
    channel_state["last_run"] = now_iso()


# ─── Minecraft pipeline ───────────────────────────────────────────────────────

def run_minecraft(state: dict, dry_run: bool = False):
    mc = state["minecraft"]
    url = pick_next_url(mc)
    if not url:
        return

    log(f"🎮 [MINECRAFT] Starting auto-generation from: {url}")

    if not dry_run:
        # 1. Generate the short
        gen_script = SCRIPT_DIR / "video_generator.py"
        result = subprocess.run(
            ["python3", str(gen_script), "--action", "generate", "--url", url],
            cwd=str(PROJECT_DIR),
            capture_output=False,
        )
        if result.returncode != 0:
            log("  ❌ Minecraft generation failed.")
            return

        # 2. Upload the generated short to Minecraft channel
        upload_script = SCRIPT_DIR / "video_generator.py"
        # Derive a title from the URL (timestamp-based fallback)
        from urllib.parse import urlparse, parse_qs
        try:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            vid_id = qs.get("v", [parsed.path.split("/")[-1]])[0][:11]
        except Exception:
            vid_id = "clip"
        auto_title = f"Minecraft Shorts | Best Shader Moments | {vid_id}"
        auto_desc = (
            "Looking for the best ultra-realistic shaders for Minecraft Pocket Edition (MCPE) and Minecraft Bedrock Edition that work smoothly on lightweight, low-end, and mid-range devices?\n"
            "In this video, we showcase BSL Shaders, SEUS Shaders, Complementary Shaders featuring stunning graphics, realistic lighting, beautiful skies, enhanced water reflections, volumetric fog, dynamic shadows, and an immersive next-generation visual experience—all without requiring a high-end phone or an RTX graphics card!\n\n"
            "✨ Key Features\n"
            "Performance: Lightweight, FPS-friendly, and optimized for low-end devices.\n"
            "Visuals: Enhanced sky, realistic clouds, vibrant colors, and improved water visuals.\n"
            "Lighting: Better sunlight, realistic moonlight, and dynamic shadow effects.\n"
            "Atmosphere: Smooth atmospheric effects and volumetric fog.\n"
            "Accessibility: 100% FREE to download with No RTX Required.\n\n"
            "🔗 Download Links\n"
            "👉 Get all the shaders featured in this video here: 👇\n"
            "https://www.piglixmcmods.dev/\n\n"
            "💬 Join the Conversation!\n"
            "Which shader was your favorite? Comment the name below! 👇\n"
            "What shader pack or mod should I review next? Let me know in the comments!\n"
            "Don't forget to Like and Subscribe for more Minecraft Bedrock content! 👍\n\n"
            "🔍 SEO & Keywords (Search Optimization)\n"
            "BSL, Newb, SEUS, SLS, Complementary realistic minecraft shaders, mcpe shaders, render dragon shaders, low-end device shaders, no lag shaders, minecraft, minecraft shaders, realistic minecraft, minecraft mod, minecraft texture pack, minecraft java, minecraft bedrock, best minecraft shaders, gaming shorts, viral minecraft, shader pack tutorial.\n\n"
            "🏷️ Tags\n"
            "#MinecraftPE #MinecraftShaders #MCPE #BedrockEdition #patchshaders #mcpeshaders #BSLShaders #NewbShaders #SEUSShaders #SLSShaders #ComplementaryShaders"
        )

        result2 = subprocess.run(
            ["python3", str(upload_script),
             "--action", "upload",
             "--title", auto_title,
             "--description", auto_desc,
             "--channel", "minecraft"],
            cwd=str(PROJECT_DIR),
            capture_output=False,
        )
        if result2.returncode == 0:
            log(f"  ✅ Minecraft short uploaded! Title: {auto_title}")
        else:
            log("  ❌ Minecraft upload failed.")
    else:
        log(f"  [DRY RUN] Would generate + upload Minecraft short from: {url}")

    mark_url_used(mc, url)
    schedule_next_run(mc)


# ─── MrBeast pipeline ─────────────────────────────────────────────────────────

def run_mrbeast(state: dict, dry_run: bool = False):
    mb = state["mrbeast"]
    clip_queue = mb.get("clip_queue", [])

    # Check if there are pending clips in the queue
    pending = [c for c in clip_queue if not c.get("uploaded", False)]

    if pending:
        clip = pending[0]
        log(f"🎯 [MRBEAST] Uploading queued clip: {clip['file']} — "{clip['title']}"")
        if not dry_run:
            video_path = OUTPUT_DIR / clip["file"]
            if not video_path.exists():
                log(f"  ⚠ File missing: {video_path}. Marking as uploaded and skipping.")
                clip["uploaded"] = True
                write_state(state)
                return

            upload_script = SCRIPT_DIR / "video_generator.py"
            result = subprocess.run(
                ["python3", str(upload_script),
                 "--action", "upload",
                 "--title", clip["title"],
                 "--description", clip.get("description", ""),
                 "--channel", "mrbeast",
                 "--video", str(video_path)],
                cwd=str(PROJECT_DIR),
                capture_output=False,
            )
            if result.returncode == 0:
                clip["uploaded"] = True
                log(f"  ✅ Uploaded: {clip['file']}")
            else:
                log("  ❌ Upload failed. Will retry next cycle.")
                return
        else:
            log(f"  [DRY RUN] Would upload queued clip: {clip['file']}")
            clip["uploaded"] = True

        mb["clip_queue"] = clip_queue
        schedule_next_run(mb)
        return

    # Queue is empty — generate a new batch of 5 clips
    url = pick_next_url(mb)
    if not url:
        return

    log(f"🎯 [MRBEAST] Queue empty. Generating 5 clips from: {url}")

    if not dry_run:
        gen_script = SCRIPT_DIR / "mrbeast_generator.py"
        result = subprocess.run(
            ["python3", str(gen_script), "--url", url],
            cwd=str(PROJECT_DIR),
            capture_output=False,
        )
        if result.returncode != 0:
            log("  ❌ MrBeast generation failed.")
            return

        # Discover all generated clips (mrbeast_clip_N.mp4)
        clip_files = sorted(OUTPUT_DIR.glob("mrbeast_clip_*.mp4"))
        if not clip_files:
            log("  ❌ No clip files found after generation.")
            return

        # Read clip titles from gemini state stored in a temp JSON (if available)
        # Fallback: generate numbered titles with MrBeast branding
        new_queue = []
        for i, f in enumerate(clip_files, 1):
            # Try to read the stored script/title from work dir
            work_title_file = PROJECT_DIR / "public" / "output" / "mrbeast_work" / f"clip_{i}" / "vo_script.txt"
            if work_title_file.exists():
                hook = work_title_file.read_text(encoding="utf-8").strip()[:80]
                title = f"MrBeast — {hook}"
            else:
                title = f"MrBeast Is INSANE! #shorts #{i}"

            copyright_disclaimer = (
                "----------------------------------------------------------------\n"
                "⚠️ COPYRIGHT DISCLAIMER:\n"
                "This video features materials protected by the Fair Use guidelines of "
                "Section 107 of the Copyright Act. All rights and credits go directly "
                "to the respective owners. No copyright infringement intended.\n\n"
                "For any inquiries or clip removals, please reach out via email!\n"
                "----------------------------------------------------------------"
            )

            new_queue.append({
                "file": f.name,
                "title": title,
                "description": copyright_disclaimer,
                "uploaded": False,
                "source_url": url,
                "created_at": now_iso(),
            })

        mb["clip_queue"] = new_queue
        log(f"  ✅ Queued {len(new_queue)} clips.")

        # Upload the first clip immediately
        first = new_queue[0]
        log(f"  📤 Uploading first clip: {first['file']}")
        upload_script = SCRIPT_DIR / "video_generator.py"
        result2 = subprocess.run(
            ["python3", str(upload_script),
             "--action", "upload",
             "--title", first["title"],
             "--description", first["description"],
             "--channel", "mrbeast",
             "--video", str(OUTPUT_DIR / first["file"])],
            cwd=str(PROJECT_DIR),
            capture_output=False,
        )
        if result2.returncode == 0:
            first["uploaded"] = True
            log(f"  ✅ First clip uploaded: {first['title']}")
        else:
            log("  ❌ First clip upload failed.")
    else:
        log(f"  [DRY RUN] Would generate 5 clips from: {url} and upload the first.")

    mark_url_used(mb, url)
    schedule_next_run(mb)


# ─── Main loop ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Auto Scheduler")
    parser.add_argument("--test", action="store_true", help="Dry run — print actions without executing")
    args = parser.parse_args()

    log("=" * 60)
    log("🤖 Auto Scheduler started" + (" [DRY RUN MODE]" if args.test else ""))
    log("=" * 60)

    # Write our PID so the UI can check if we're running
    state = read_state()
    state["scheduler_pid"] = os.getpid()
    write_state(state)

    try:
        while True:
            state = read_state()

            # ── Minecraft ──────────────────────────────────────────────────
            mc = state.get("minecraft", {})
            if mc.get("is_running") and is_due(mc.get("next_run")):
                log("⏰ Minecraft run triggered!")
                try:
                    run_minecraft(state, dry_run=args.test)
                except Exception as e:
                    log(f"  ❌ Minecraft run error: {e}")
                write_state(state)

            # ── MrBeast ───────────────────────────────────────────────────
            mb = state.get("mrbeast", {})
            if mb.get("is_running") and is_due(mb.get("next_run")):
                log("⏰ MrBeast run triggered!")
                try:
                    run_mrbeast(state, dry_run=args.test)
                except Exception as e:
                    log(f"  ❌ MrBeast run error: {e}")
                write_state(state)

            if args.test:
                log("Test run complete. Exiting.")
                break

            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        log("🛑 Scheduler stopped by user.")
        state = read_state()
        state["scheduler_pid"] = None
        write_state(state)


if __name__ == "__main__":
    main()
