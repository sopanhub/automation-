import { NextResponse } from 'next/server';
import { execFile } from 'child_process';
import path from 'path';

export async function POST(request) {
  try {
    const { title, description } = await request.json();

    if (!title || !description) {
      return NextResponse.json({ error: 'Title and description are required' }, { status: 400 });
    }

    if (!process.env.YOUTUBE_CLIENT_ID || !process.env.YOUTUBE_CLIENT_SECRET || !process.env.YOUTUBE_REFRESH_TOKEN) {
      return NextResponse.json(
        {
          error:
            'Server is missing YouTube credentials. Add YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN to your .env file.',
        },
        { status: 500 }
      );
    }

    const scriptPath = path.join(process.cwd(), 'scripts', 'video_generator.py');

    return new Promise((resolve) => {
      execFile(
        'python3',
        [scriptPath, '--action', 'upload', '--title', title, '--description', description],
        (error, stdout, stderr) => {
          if (error) {
            console.error('Python Error:', error);
            resolve(NextResponse.json({ error: 'Failed to upload video', details: stderr }, { status: 500 }));
          } else {
            resolve(NextResponse.json({ success: true, stdout }, { status: 200 }));
          }
        }
      );
    });
  } catch (error) {
    console.error(error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
