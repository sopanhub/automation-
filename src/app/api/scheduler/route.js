import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const STATE_PATH = path.join(process.cwd(), 'scheduler_state.json');

function readState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_PATH, 'utf-8'));
  } catch {
    return {
      minecraft: { urls: [], used_urls: [], is_running: false, next_run: null, last_run: null, interval_hours: 5 },
      mrbeast: { urls: [], used_urls: [], clip_queue: [], is_running: false, next_run: null, last_run: null, interval_hours: 5 },
      scheduler_pid: null,
    };
  }
}

function writeState(state) {
  fs.writeFileSync(STATE_PATH, JSON.stringify(state, null, 2), 'utf-8');
}

// ── GET: return full state ─────────────────────────────────────────────────
export async function GET() {
  const state = readState();
  // Enrich with human-readable countdowns
  const now = Date.now();
  for (const ch of ['minecraft', 'mrbeast']) {
    const s = state[ch];
    if (s.next_run) {
      const diff = new Date(s.next_run).getTime() - now;
      s.next_run_in_ms = diff > 0 ? diff : 0;
      const mins = Math.floor((s.next_run_in_ms / 1000) / 60);
      const hrs  = Math.floor(mins / 60);
      s.next_run_label = hrs > 0 ? `${hrs}h ${mins % 60}m` : `${mins}m`;
    } else {
      s.next_run_label = 'Not scheduled';
    }
  }
  return NextResponse.json(state);
}

// ── POST: control scheduler ────────────────────────────────────────────────
export async function POST(request) {
  const body = await request.json();
  const { action, channel, interval_hours } = body;
  const state = readState();

  if (action === 'start' && channel) {
    const hours = interval_hours || state[channel].interval_hours || 5;
    state[channel].is_running = true;
    state[channel].interval_hours = hours;
    // Set next run to now + interval so it runs after the first interval
    state[channel].next_run = new Date(Date.now() + hours * 60 * 60 * 1000).toISOString();
    writeState(state);
    return NextResponse.json({ success: true, message: `Scheduler started for ${channel}. Next run in ${hours}h.` });
  }

  if (action === 'stop' && channel) {
    state[channel].is_running = false;
    state[channel].next_run = null;
    writeState(state);
    return NextResponse.json({ success: true, message: `Scheduler stopped for ${channel}.` });
  }

  if (action === 'trigger_now' && channel) {
    // Set next run to NOW so the scheduler picks it up immediately
    state[channel].next_run = new Date(Date.now() - 1000).toISOString();
    if (!state[channel].is_running) {
      state[channel].is_running = true;
    }
    writeState(state);
    // Directly invoke the scheduler API action
    return NextResponse.json({ success: true, message: `Triggered immediate run for ${channel}.` });
  }

  if (action === 'set_interval' && channel) {
    const hours = interval_hours || 5;
    state[channel].interval_hours = hours;
    writeState(state);
    return NextResponse.json({ success: true, message: `Interval set to ${hours}h for ${channel}.` });
  }

  if (action === 'clear_queue' && channel === 'mrbeast') {
    state.mrbeast.clip_queue = [];
    writeState(state);
    return NextResponse.json({ success: true, message: 'MrBeast clip queue cleared.' });
  }

  return NextResponse.json({ error: 'Unknown action' }, { status: 400 });
}
