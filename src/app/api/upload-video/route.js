import { NextResponse } from 'next/server';
import { execFile } from 'child_process';
import path from 'path';

export async function POST(request) {
  try {
    const { title, description, channel = 'minecraft', videoFilename } = await request.json();

    if (!title || !description) {
      return NextResponse.json({ error: 'Title and description are required' }, { status: 400 });
    }

    const prefix = channel.toUpperCase() + '_';
    if (!process.env[`${prefix}YOUTUBE_CLIENT_ID`] || !process.env[`${prefix}YOUTUBE_CLIENT_SECRET`] || !process.env[`${prefix}YOUTUBE_REFRESH_TOKEN`]) {
      return NextResponse.json(
        {
          error:
            `Server is missing YouTube credentials for ${channel}. Add ${prefix}YOUTUBE_CLIENT_ID, ${prefix}YOUTUBE_CLIENT_SECRET and ${prefix}YOUTUBE_REFRESH_TOKEN to your .env file.`,
        },
        { status: 500 }
      );
    }

    const scriptPath = path.join(process.cwd(), 'scripts', 'video_generator.py');
    const args = [scriptPath, '--action', 'upload', '--title', title, '--description', description, '--channel', channel];

    if (videoFilename) {
      // Safely resolve the path for the requested video file inside the public/output folder
      const videoPath = path.join(process.cwd(), 'public', 'output', path.basename(videoFilename));
      args.push('--video', videoPath);
    }

    return new Promise((resolve) => {
      execFile(
        'python3',
        args,
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
