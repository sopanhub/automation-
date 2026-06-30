import { NextResponse } from 'next/server';

export async function POST(request) {
  try {
    const { prompt, currentState } = await request.json();
    const finalApiKey = process.env.GROQ_API_KEY;

    if (!prompt) {
      return NextResponse.json({ error: 'Prompt is required' }, { status: 400 });
    }

    if (!finalApiKey) {
      return NextResponse.json({ error: 'Server is missing Groq API Key' }, { status: 500 });
    }

    const systemPrompt = `You are an AI Video Editor Assistant. The user wants to magically edit their video settings.
Your job is to read their request and output ONLY a JSON object that maps to the new state.

The current state is: ${JSON.stringify(currentState)}

Available Voice Options (Edge TTS):
- en-US-GuyNeural (Crisp Male)
- en-US-ChristopherNeural (Deep Male)
- en-US-AriaNeural (Clear Female)
- en-US-SteffanNeural (Deep Male 2)
- en-US-JennyNeural (Standard Female)

Available Colors: yellow, red, white, green, blue, black, magenta, cyan
Available Positions: top, center, bottom

Task: Read the user's request. Modify ONLY the fields they implicitly or explicitly requested to change.
Output format MUST be EXACTLY: { "voice": "...", "captionColor": "...", "captionPosition": "..." }

User Request: "${prompt}"`;

    const groqUrl = `https://api.groq.com/openai/v1/chat/completions`;
    const groqResponse = await fetch(groqUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${finalApiKey}`
      },
      body: JSON.stringify({
        model: 'llama-3.1-8b-instant',
        messages: [{ role: 'system', content: systemPrompt }],
        temperature: 0.2,
        response_format: { type: 'json_object' }
      })
    });

    const groqData = await groqResponse.json();
    if (!groqResponse.ok) {
      throw new Error(groqData.error?.message || 'Failed to generate config from Groq');
    }

    let result;
    try {
      result = JSON.parse(groqData.choices[0].message.content);
    } catch (parseError) {
      throw new Error("Groq API returned invalid JSON: " + groqData.choices[0].message.content);
    }

    return NextResponse.json(result);

  } catch (error) {
    console.error('Magic Edit Error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
