import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

function isLikelyUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}

export async function POST(request) {
  try {
    const body = await request.json();
    const { urls } = body || {};

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return NextResponse.json(
        { error: 'Server is missing GEMINI_API_KEY. Add it to your .env file and restart the server.' },
        { status: 500 }
      );
    }

    const urlList = (Array.isArray(urls) ? urls : urls ? [urls] : [])
      .map((u) => String(u).trim())
      .filter(Boolean);

    if (urlList.length === 0) {
      return NextResponse.json({ error: 'Provide at least one source video URL.' }, { status: 400 });
    }

    const invalid = urlList.filter((u) => !isLikelyUrl(u));
    if (invalid.length > 0) {
      return NextResponse.json(
        { error: `These don't look like valid URLs: ${invalid.join(', ')}` },
        { status: 400 }
      );
    }

    // Only the first URL is analyzed by Gemini today; the script is built
    // around a single source short. Extra URLs are accepted for future use
    // but we surface a note so the user understands current behavior.
    const scriptPath = path.join(process.cwd(), 'scripts', 'video_generator.py');
    const musicPath = path.join(process.cwd(), 'scripts', 'music.mp3');
    const urlsJson = JSON.stringify(urlList);

    const stream = new ReadableStream({
      start(controller) {
        const send = (obj) => controller.enqueue(new TextEncoder().encode(JSON.stringify(obj) + '\n'));

        send({ type: 'log', message: 'Starting Gemini video analysis…\n' });
        if (urlList.length > 1) {
          send({
            type: 'log',
            message: `Note: only the first URL is analyzed for shader before/after moments. Extra URLs are ignored for now.\n`,
          });
        }

        const pythonProcess = spawn(
          'python3',
          [scriptPath, '--action', 'generate', '--sources', urlsJson, '--music', musicPath],
          {
            env: {
              ...process.env,
              PYTHONUNBUFFERED: '1',
              GEMINI_API_KEY: apiKey.trim(),
            },
          }
        );

        request.signal.addEventListener('abort', () => {
          pythonProcess.kill();
        });

        pythonProcess.stdout.on('data', (data) => send({ type: 'log', message: data.toString() }));
        pythonProcess.stderr.on('data', (data) => send({ type: 'log', message: data.toString() }));

        pythonProcess.on('close', (code) => {
          if (code === 0) {
            send({ type: 'success' });
          } else {
            send({ type: 'error', message: `Python script exited with code ${code}` });
          }
          controller.close();
        });

        pythonProcess.on('error', (err) => {
          send({ type: 'error', message: `Failed to start python3: ${err.message}` });
          controller.close();
        });
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'application/x-ndjson',
        'Cache-Control': 'no-cache',
      },
    });
  } catch (error) {
    console.error(error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
