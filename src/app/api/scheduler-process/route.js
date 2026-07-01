import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const STATE_PATH = path.join(process.cwd(), 'scheduler_state.json');
const SCRIPT_PATH = path.join(process.cwd(), 'scripts', 'auto_scheduler.py');

function readState() {
  try { return JSON.parse(fs.readFileSync(STATE_PATH, 'utf-8')); }
  catch { return {}; }
}
function writeState(state) {
  fs.writeFileSync(STATE_PATH, JSON.stringify(state, null, 2), 'utf-8');
}

function isPidAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

// ── GET: check if scheduler process is alive ───────────────────────────────
export async function GET() {
  const state = readState();
  const pid = state.scheduler_pid;
  const alive = isPidAlive(pid);
  if (!alive && pid) {
    state.scheduler_pid = null;
    writeState(state);
  }
  return NextResponse.json({ running: alive, pid: alive ? pid : null });
}

// ── POST: start or stop the scheduler process ──────────────────────────────
export async function POST(request) {
  const { action } = await request.json();
  const state = readState();

  if (action === 'start') {
    if (isPidAlive(state.scheduler_pid)) {
      return NextResponse.json({ success: true, message: 'Scheduler already running.', pid: state.scheduler_pid });
    }
    const child = spawn('python3', [SCRIPT_PATH], {
      detached: true,
      stdio: 'ignore',
      cwd: process.cwd(),
    });
    child.unref();
    state.scheduler_pid = child.pid;
    writeState(state);
    return NextResponse.json({ success: true, message: 'Scheduler process started.', pid: child.pid });
  }

  if (action === 'stop') {
    const pid = state.scheduler_pid;
    if (!pid || !isPidAlive(pid)) {
      state.scheduler_pid = null;
      writeState(state);
      return NextResponse.json({ success: true, message: 'Scheduler was not running.' });
    }
    try {
      process.kill(pid, 'SIGTERM');
      state.scheduler_pid = null;
      writeState(state);
      return NextResponse.json({ success: true, message: 'Scheduler stopped.' });
    } catch (e) {
      return NextResponse.json({ error: `Failed to stop: ${e.message}` }, { status: 500 });
    }
  }

  return NextResponse.json({ error: 'Unknown action' }, { status: 400 });
}
