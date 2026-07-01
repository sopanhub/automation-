import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const STATE_PATH = path.join(process.cwd(), 'scheduler_state.json');

function readState() {
  try { return JSON.parse(fs.readFileSync(STATE_PATH, 'utf-8')); }
  catch { return { minecraft: { urls: [], used_urls: [] }, mrbeast: { urls: [], used_urls: [], clip_queue: [] } }; }
}
function writeState(state) {
  fs.writeFileSync(STATE_PATH, JSON.stringify(state, null, 2), 'utf-8');
}

// ── GET: list URLs for a channel ───────────────────────────────────────────
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const channel = searchParams.get('channel');
  const state = readState();
  const ch = state[channel];
  if (!ch) return NextResponse.json({ error: 'Invalid channel' }, { status: 400 });
  return NextResponse.json({ urls: ch.urls || [], used_urls: ch.used_urls || [] });
}

// ── POST: add a URL ────────────────────────────────────────────────────────
export async function POST(request) {
  const { channel, url } = await request.json();
  if (!channel || !url) return NextResponse.json({ error: 'channel and url required' }, { status: 400 });

  const state = readState();
  if (!state[channel]) return NextResponse.json({ error: 'Invalid channel' }, { status: 400 });

  const allUrls = [...(state[channel].urls || []), ...(state[channel].used_urls || [])];
  if (allUrls.includes(url)) {
    return NextResponse.json({ error: 'URL already exists in library' }, { status: 409 });
  }

  state[channel].urls = [...(state[channel].urls || []), url];
  writeState(state);
  return NextResponse.json({ success: true, urls: state[channel].urls });
}

// ── DELETE: remove a URL ───────────────────────────────────────────────────
export async function DELETE(request) {
  const { channel, url } = await request.json();
  if (!channel || !url) return NextResponse.json({ error: 'channel and url required' }, { status: 400 });

  const state = readState();
  if (!state[channel]) return NextResponse.json({ error: 'Invalid channel' }, { status: 400 });

  state[channel].urls = (state[channel].urls || []).filter(u => u !== url);
  state[channel].used_urls = (state[channel].used_urls || []).filter(u => u !== url);
  writeState(state);
  return NextResponse.json({ success: true });
}
