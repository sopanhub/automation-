# Shader Short Automation

Paste a YouTube URL of a Minecraft shader comparison video. Gemini watches it,
finds the clearest before/after shader moments (and reads the shader names on
screen), then a Python pipeline cuts a ~30-second vertical short:

```
[Before #1 5s][After #1 5s][Before #2 5s][After #2 5s][Before #3 5s][After #3 5s]
```

with a generated voiceover (Edge TTS) and word-synced captions burned in,
ready to preview and upload straight to YouTube.

## How it works

1. **Frontend** (`src/app/page.js`) — paste a URL, click Generate.
2. **`/api/generate-video`** — validates the URL, then spawns
   `scripts/video_generator.py --action generate` and streams its logs back
   to the browser.
3. **`scripts/video_generator.py`**:
   - Downloads the source video with `yt-dlp`.
   - Uploads it to the Gemini Files API and asks `gemini-2.5-flash` for 3
     before/after timestamp pairs plus the shader name shown in each.
   - Cuts 6 clips (3 pairs × before/after), 5s each.
   - Writes a short voiceover script per pair, synthesizes it with
     `edge-tts`, and gets word-level timing for free via the `.vtt` it
     generates.
   - Burns in synced captions, ducks background music under the voiceover,
     and renders the final vertical MP4 to `public/output/upload.mp4`.
4. **`/api/upload-video`** — optionally uploads the result straight to
   YouTube using stored OAuth credentials.
5. **`/api/magic-edit`** (optional) — a small Groq-powered assistant that
   lets you describe voice/caption tweaks in plain English.

## Setup

### 1. Install JS dependencies

```bash
npm install
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

You'll also need `ffmpeg` installed and on your `PATH` (used by `moviepy`
and `ffprobe`).

### 3. Configure environment variables

```bash
cp .env.example .env
```

Then fill in `.env`:

- `GEMINI_API_KEY` — **required**. Get one at
  [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
- `GROQ_API_KEY` — optional, only needed for the "Magic Edit" assistant.
- `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_REFRESH_TOKEN` —
  optional, only needed if you want the "Upload to YouTube" button to work.
  Create OAuth credentials in the
  [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
  (YouTube Data API v3 enabled) and generate a refresh token once via the
  standard OAuth installed-app flow.

### 4. Run the dev server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Notes

- Only the first source URL is currently analyzed by Gemini — the script is
  built around finding before/after pairs within a single source video.
- Generated videos are written to `public/output/` and are **not** committed
  to git (see `.gitignore`); each run regenerates them.
- Never commit a real API key. `.env` is gitignored; only `.env.example`
  (with empty values) should be tracked.
