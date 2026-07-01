import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const OUTPUT_DIR = path.join(process.cwd(), 'public', 'output');

const VIDEO_EXTS = new Set(['.mp4', '.webm', '.mov']);

// ── GET: list all video files ──────────────────────────────────────────────
export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const channel = searchParams.get('channel') || 'all'; // 'minecraft' | 'mrbeast' | 'all'

    const files = fs.readdirSync(OUTPUT_DIR, { withFileTypes: true })
      .filter(d => !d.isDirectory())
      .filter(d => VIDEO_EXTS.has(path.extname(d.name).toLowerCase()))
      .map(d => {
        const filePath = path.join(OUTPUT_DIR, d.name);
        const stat = fs.statSync(filePath);
        return {
          name: d.name,
          url: `/output/${d.name}`,
          sizeBytes: stat.size,
          sizeMB: (stat.size / (1024 * 1024)).toFixed(2),
          createdAt: stat.birthtime.toISOString(),
          channel: d.name.startsWith('mrbeast') ? 'mrbeast' : 'minecraft',
        };
      })
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

    const filtered = channel === 'all' ? files : files.filter(f => f.channel === channel);
    return NextResponse.json({ files: filtered });
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

// ── DELETE: remove a file by name ─────────────────────────────────────────
export async function DELETE(request) {
  try {
    const { filename } = await request.json();
    if (!filename) return NextResponse.json({ error: 'filename required' }, { status: 400 });

    // Safety: only allow simple file names, no path traversal
    const basename = path.basename(filename);
    const filePath = path.join(OUTPUT_DIR, basename);

    if (!filePath.startsWith(OUTPUT_DIR)) {
      return NextResponse.json({ error: 'Invalid file path' }, { status: 400 });
    }
    if (!fs.existsSync(filePath)) {
      return NextResponse.json({ error: 'File not found' }, { status: 404 });
    }

    fs.unlinkSync(filePath);
    return NextResponse.json({ success: true, deleted: basename });
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
