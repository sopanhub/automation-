'use client';

import { useState, useRef } from 'react';

export default function Dashboard() {
  const [url, setUrl]                       = useState('');
  const [status, setStatus]                 = useState('Idle');
  const [logs, setLogs]                     = useState([]);
  const [videoGenerated, setVideoGenerated] = useState(false);
  const [loading, setLoading]               = useState(false);
  const [uploadTitle, setUploadTitle]       = useState('');
  const [uploadDescription, setUploadDescription] = useState('');
  const videoRef = useRef(null);

  // ── Logs ─────────────────────────────────────────────────────────────────

  const addLog = (msg) =>
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);

  // ── Generate ─────────────────────────────────────────────────────────────

  const handleRunAutomation = async () => {
    if (!url.trim()) {
      alert('Paste a YouTube video URL first.');
      return;
    }

    setLoading(true);
    setVideoGenerated(false);
    setLogs([]);
    setStatus('Analyzing video with Gemini…');
    addLog(`Starting automation for: ${url.trim()}`);

    try {
      const response = await fetch('/api/generate-video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: [url.trim()] }),
      });

      if (!response.ok) {
        let errorMsg = 'Unknown error';
        try {
          const errData = await response.json();
          errorMsg = errData.error || response.statusText;
        } catch (e) {}
        addLog('❌ Error: ' + errorMsg);
        setStatus('❌ Generation Failed.');
        setLoading(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep the last incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const parsed = JSON.parse(line);
            if (parsed.type === 'log') {
              addLog(parsed.message.trim());
              if (parsed.message.includes('Analysing video with Gemini')) {
                setStatus('Watching video for shader before/after moments…');
              } else if (parsed.message.includes('Assembling alternating video clips')) {
                setStatus('Cutting before/after clips…');
              } else if (parsed.message.includes('Writing final video')) {
                setStatus('Rendering final short…');
              }
            } else if (parsed.type === 'success') {
              setStatus('✅ Short generated successfully!');
              setVideoGenerated(true);
            } else if (parsed.type === 'error') {
              addLog('❌ Error: ' + parsed.message);
              setStatus('❌ Generation Failed.');
            }
          } catch (e) {
            console.error('Failed to parse stream line:', line, e);
          }
        }
      }
    } catch (err) {
      addLog('❌ Network Error: ' + err.message);
      setStatus('❌ Generation Failed.');
    } finally {
      setLoading(false);
    }
  };

  // ── Upload ────────────────────────────────────────────────────────────────

  const handleUpload = async () => {
    if (!uploadTitle.trim() || !uploadDescription.trim()) {
      alert('Add a title and description before uploading.');
      return;
    }
    setLoading(true);
    setStatus('Uploading to YouTube...');
    addLog('Initiating YouTube upload...');

    try {
      const response = await fetch('/api/upload-video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: uploadTitle.trim(), description: uploadDescription.trim() }),
      });
      const data = await response.json();

      if (response.ok) {
        addLog('✅ Upload successful!\n' + data.stdout);
        setStatus('✅ Uploaded to YouTube!');
      } else {
        addLog('❌ Upload error: ' + data.error);
        if (data.details) addLog('Details: ' + data.details);
        setStatus('❌ Upload Failed.');
      }
    } catch (err) {
      addLog('❌ Network Error: ' + err.message);
      setStatus('❌ Upload Failed.');
    } finally {
      setLoading(false);
    }
  };

  // ── Timeline shown to the user (matches the actual Python pipeline) ───────
  const seqLabels = [
    { time: '0–5s',   icon: '⬛', label: 'Before #1', desc: 'Vanilla Minecraft, no shaders' },
    { time: '5–10s',  icon: '✨', label: 'After #1',  desc: 'Shader #1 revealed (Gemini names it)' },
    { time: '10–15s', icon: '⬛', label: 'Before #2', desc: 'Vanilla again' },
    { time: '15–20s', icon: '✨', label: 'After #2',  desc: 'Shader #2 revealed' },
    { time: '20–25s', icon: '⬛', label: 'Before #3', desc: 'Vanilla again' },
    { time: '25–30s', icon: '✨', label: 'After #3',  desc: 'Shader #3 revealed' },
  ];

  return (
    <div style={s.page}>
      {/* ── Header ── */}
      <div style={s.header}>
        <h1 style={s.title}>🎬 Shader Short Automation</h1>
        <p style={s.subtitle}>
          Paste a <strong>Minecraft shader comparison video URL</strong> → Gemini watches it and
          finds the before/after shader moments and names → produces a synced
          <strong> ~30-second vertical short</strong> with voiceover and captions, automatically.
        </p>
      </div>

      <div style={s.grid}>
        {/* ── Left: Config ── */}
        <div style={s.card}>
          <h2 style={s.cardTitle}>⚙️ Source Video</h2>

          <div style={s.urlSection}>
            <label style={s.label}>YouTube video URL</label>
            <input
              id="url-input"
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=..."
              style={s.input}
              disabled={loading}
            />
            <p style={s.urlTip}>
              💡 Use a video that already shows multiple shaders being toggled on/off —
              Gemini finds the clearest before/after moments and reads the shader names on screen.
            </p>
          </div>

          {/* Timeline */}
          <div style={s.timeline}>
            <p style={s.tlTitle}>📋 Output Short Structure (~30s)</p>
            {seqLabels.map((seq) => (
              <div key={seq.time} style={s.tlRow}>
                <span style={s.tlTime}>{seq.time}</span>
                <span style={s.tlIcon}>{seq.icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={s.tlLabel}>{seq.label}</div>
                  <div style={s.tlDesc}>{seq.desc}</div>
                </div>
              </div>
            ))}
          </div>

          <button
            id="run-automation-btn"
            onClick={handleRunAutomation}
            disabled={loading}
            style={{ ...s.btn, ...(loading ? s.btnDisabled : {}) }}
          >
            {loading && !videoGenerated
              ? '⏳ Processing… (this takes a few minutes)'
              : '🚀 Generate Short'}
          </button>
        </div>

        {/* ── Right: Preview & Upload ── */}
        <div style={s.card}>
          <h2 style={s.cardTitle}>🎥 Preview &amp; Upload</h2>

          {videoGenerated ? (
            <div>
              {/* vertical short player */}
              <div style={s.videoWrap}>
                <video
                  id="preview-video"
                  ref={videoRef}
                  src="/output/upload.mp4"
                  controls
                  style={s.video}
                />
              </div>

              <div style={s.metaPanel}>
                <label style={s.label}>Title</label>
                <input
                  id="upload-title"
                  type="text"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  placeholder="Top 3 Minecraft Shaders You NEED"
                  style={{ ...s.input, marginBottom: 14 }}
                  disabled={loading}
                />
                <label style={s.label}>Description</label>
                <textarea
                  id="upload-description"
                  value={uploadDescription}
                  onChange={(e) => setUploadDescription(e.target.value)}
                  placeholder="Links to all 3 shaders in the comments! #minecraft #shaders"
                  style={s.textarea}
                  disabled={loading}
                />
              </div>

              <button
                id="upload-youtube-btn"
                onClick={handleUpload}
                disabled={loading}
                style={{ ...s.btnUpload, ...(loading ? s.btnDisabled : {}) }}
              >
                {loading && videoGenerated ? '⏳ Uploading…' : '📤 Upload to YouTube'}
              </button>
            </div>
          ) : (
            <div style={s.placeholder}>
              <div style={s.phIcon}>🎬</div>
              <p style={s.phText}>No short generated yet.</p>
              <p style={s.phSub}>
                Paste a video URL and click <strong>Generate Short</strong>.<br />
                Gemini will watch it, find before/after shader moments, write a matching
                voiceover, and produce a <strong>~30-second vertical MP4</strong> with synced
                captions.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* ── Logs ── */}
      <div style={{ ...s.card, marginTop: 24 }}>
        <div style={s.logsHeader}>
          <h2 style={s.cardTitle}>📟 Status: {status}</h2>
          {logs.length > 0 && (
            <button id="clear-logs-btn" style={s.clearBtn} onClick={() => setLogs([])}>
              Clear
            </button>
          )}
        </div>
        <div id="logs-panel" style={s.logs}>
          {logs.length === 0
            ? <span style={{ color: '#334155' }}>Logs will appear here when automation runs…</span>
            : logs.map((line, i) => <div key={i} style={s.logLine}>{line}</div>)
          }
        </div>
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const s = {
  page: {
    maxWidth: '1280px', margin: '0 auto', padding: '40px 24px',
    fontFamily: "'Inter', 'system-ui', -apple-system, sans-serif",
    backgroundColor: '#060b14', color: '#e2e8f0', minHeight: '100vh',
  },
  header: { textAlign: 'center', marginBottom: 40 },
  title: {
    fontSize: '2.4rem', fontWeight: 800, marginBottom: 10,
    background: 'linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #34d399 100%)',
    WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', letterSpacing: '-0.5px',
  },
  subtitle: { color: '#64748b', fontSize: '1rem', lineHeight: 1.7, maxWidth: 760, margin: '0 auto' },

  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(440px, 1fr))', gap: 24 },

  card: {
    backgroundColor: '#0d1626', borderRadius: 16, padding: 28,
    border: '1px solid #1a2640', boxShadow: '0 8px 32px rgba(0,0,0,0.45)',
  },
  cardTitle: {
    fontSize: '1.1rem', fontWeight: 700, marginBottom: 20, color: '#cbd5e1',
    borderBottom: '1px solid #1a2640', paddingBottom: 12,
  },

  // URL input
  urlSection: { marginBottom: 20 },
  urlTip:    { fontSize: '0.78rem', color: '#334155', marginTop: 10, lineHeight: 1.6 },

  label: {
    display: 'block', marginBottom: 8, fontWeight: 600, color: '#64748b',
    fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em',
  },
  input: {
    width: '100%', padding: '12px 14px', borderRadius: 10, border: '1px solid #1a2640',
    backgroundColor: '#060b14', color: '#f1f5f9', fontSize: '0.92rem',
    outline: 'none', boxSizing: 'border-box',
  },
  textarea: {
    width: '100%', padding: '12px 14px', borderRadius: 10, border: '1px solid #1a2640',
    backgroundColor: '#060b14', color: '#f1f5f9', fontSize: '0.88rem',
    outline: 'none', boxSizing: 'border-box', minHeight: 90, resize: 'vertical',
    fontFamily: 'inherit',
  },

  // Timeline
  timeline: {
    backgroundColor: '#060b14', borderRadius: 10, padding: '14px 16px',
    marginBottom: 20, border: '1px solid #1a2640',
  },
  tlTitle: { fontSize: '0.72rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 },
  tlRow:   { display: 'flex', alignItems: 'flex-start', gap: 10, padding: '7px 0', borderBottom: '1px solid #0d1626' },
  tlTime:  { fontSize: '0.7rem', fontWeight: 700, color: '#34d399', minWidth: 58, fontFamily: 'monospace', paddingTop: 1 },
  tlIcon:  { fontSize: '0.85rem', paddingTop: 1 },
  tlLabel: { fontSize: '0.8rem', fontWeight: 600, color: '#818cf8', marginBottom: 2 },
  tlDesc:  { fontSize: '0.72rem', color: '#475569', lineHeight: 1.4 },

  btn: {
    width: '100%', padding: 16, borderRadius: 10, border: 'none',
    background: 'linear-gradient(135deg, #3b82f6, #818cf8)', color: '#fff',
    fontSize: '1rem', fontWeight: 700, cursor: 'pointer', letterSpacing: '0.02em',
  },
  btnUpload: {
    width: '100%', padding: 14, borderRadius: 10, border: 'none',
    background: 'linear-gradient(135deg, #ef4444, #dc2626)', color: '#fff',
    fontSize: '1rem', fontWeight: 700, cursor: 'pointer', marginTop: 16,
  },
  btnDisabled: { opacity: 0.45, cursor: 'not-allowed' },

  // Video player (vertical short)
  videoWrap: { width: '100%', maxWidth: 280, aspectRatio: '480 / 854', backgroundColor: '#000', borderRadius: 10, overflow: 'hidden', marginBottom: 16, margin: '0 auto 16px' },
  video:     { width: '100%', height: '100%', display: 'block', objectFit: 'contain' },

  // Metadata / upload form
  metaPanel: { backgroundColor: '#060b14', borderRadius: 10, padding: 16, border: '1px solid #1a2640', marginBottom: 4 },

  // Placeholder
  placeholder: {
    minHeight: 340, display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', backgroundColor: '#060b14', borderRadius: 10,
    border: '1px dashed #1a2640', padding: 40, textAlign: 'center',
  },
  phIcon: { fontSize: '2.8rem', opacity: 0.3, marginBottom: 16 },
  phText: { color: '#475569', fontSize: '1rem', fontWeight: 600, marginBottom: 8 },
  phSub:  { color: '#2d3f55', fontSize: '0.85rem', lineHeight: 1.7 },

  // Logs
  logsHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  clearBtn:   { background: 'none', border: '1px solid #1a2640', color: '#475569', padding: '4px 12px', borderRadius: 6, cursor: 'pointer', fontSize: '0.8rem' },
  logs: {
    backgroundColor: '#060b14', padding: 16, borderRadius: 10, fontFamily: 'monospace',
    fontSize: '0.78rem', color: '#34d399', maxHeight: 360, overflowY: 'auto',
    whiteSpace: 'pre-wrap', border: '1px solid #1a2640', marginTop: 12,
  },
  logLine: { marginBottom: 5, lineHeight: 1.5 },
};
