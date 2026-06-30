import { NextResponse } from 'next/server';
import { execFile } from 'child_process';
import util from 'util';

const execFileAsync = util.promisify(execFile);

export async function POST(request) {
  try {
    const { query } = await request.json();

    if (!query || typeof query !== 'string' || !query.trim()) {
      return NextResponse.json({ error: 'Missing search query' }, { status: 400 });
    }

    // execFile (not exec) so the query is passed as a real argument,
    // never interpolated into a shell string.
    const { stdout } = await execFileAsync('yt-dlp', [
      '--no-warnings',
      '--print',
      'webpage_url',
      `ytsearch20:${query.trim()}`,
    ]);

    const urls = stdout
      .split('\n')
      .map((u) => u.trim())
      .filter((u) => u.startsWith('http'));

    if (urls.length === 0) {
      return NextResponse.json({ error: 'No video found' }, { status: 404 });
    }

    const randomUrl = urls[Math.floor(Math.random() * urls.length)];
    return NextResponse.json({ url: randomUrl });
  } catch (error) {
    console.error('Search error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
