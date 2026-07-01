'use client';

import { useState, useEffect, useCallback } from 'react';

const MRBEAST_DESC = `----------------------------------------------------------------
⚠️ COPYRIGHT DISCLAIMER:
This video features materials protected by the Fair Use guidelines of Section 107 of the Copyright Act. All rights and credits go directly to the respective owners. No copyright infringement intended.

For any inquiries or clip removals, please reach out via email!
----------------------------------------------------------------`;

const MINECRAFT_DESC = `Looking for the best ultra-realistic shaders for Minecraft Pocket Edition (MCPE) and Minecraft Bedrock Edition that work smoothly on lightweight, low-end, and mid-range devices?
In this video, we showcase BSL Shaders, SEUS Shaders, Complementary Shaders featuring stunning graphics, realistic lighting, beautiful skies, enhanced water reflections, volumetric fog, dynamic shadows, and an immersive next-generation visual experience—all without requiring a high-end phone or an RTX graphics card!

✨ Key Features
Performance: Lightweight, FPS-friendly, and optimized for low-end devices.
Visuals: Enhanced sky, realistic clouds, vibrant colors, and improved water visuals.
Lighting: Better sunlight, realistic moonlight, and dynamic shadow effects.
Atmosphere: Smooth atmospheric effects and volumetric fog.
Accessibility: 100% FREE to download with No RTX Required.

🔗 Download Links
👉 Get all the shaders featured in this video here: 👇
https://www.piglixmcmods.dev/

💬 Join the Conversation!
Which shader was your favorite? Comment the name below! 👇
What shader pack or mod should I review next? Let me know in the comments!
Don't forget to Like and Subscribe for more Minecraft Bedrock content! 👍

🔍 SEO & Keywords (Search Optimization)
BSL, Newb, SEUS, SLS, Complementary realistic minecraft shaders, mcpe shaders, render dragon shaders, low-end device shaders, no lag shaders, minecraft, minecraft shaders, realistic minecraft, minecraft mod, minecraft texture pack, minecraft java, minecraft bedrock, best minecraft shaders, gaming shorts, viral minecraft, shader pack tutorial.

🏷️ Tags
#MinecraftPE #MinecraftShaders #MCPE #BedrockEdition #patchshaders #mcpeshaders #BSLShaders #NewbShaders #SEUSShaders #SLSShaders #ComplementaryShaders`;

export default function HistoryModal({ channel, onClose }) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(null);
  const [uploading, setUploading] = useState(null);
  const [error, setError] = useState(null);

  const accent = channel === 'mrbeast' ? '#ef4444' : '#22d3ee';
  const label  = channel === 'mrbeast' ? 'MrBeast' : 'Minecraft';

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/history?channel=${channel}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setFiles(data.files || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [channel]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleDelete = async (filename) => {
    if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return;
    setDeleting(filename);
    try {
      const res = await fetch('/api/history', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setFiles(prev => prev.filter(f => f.name !== filename));
    } catch (e) {
      alert('Delete failed: ' + e.message);
    } finally {
      setDeleting(null);
    }
  };

  const handleUpload = async (file) => {
    const title = window.prompt(`Enter YouTube Title for ${file.name}:`, file.name.replace('.mp4', '').replace(/_/g, ' '));
    if (!title) return;
    
    setUploading(file.name);
    try {
      const res = await fetch('/api/upload-video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          channel: file.channel,
          videoFilename: file.name,
          title: title,
          description: file.channel === 'mrbeast' ? MRBEAST_DESC : MINECRAFT_DESC,
        }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      alert('✅ Upload successful! Video ID: ' + data.videoId);
    } catch (e) {
      alert('❌ Upload failed: ' + e.message);
    } finally {
      setUploading(null);
    }
  };

  const formatDate = (iso) => {
    const d = new Date(iso);
    return d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
  };

  const formatSize = (mb) => mb < 1 ? `${(mb * 1024).toFixed(0)} KB` : `${mb} MB`;

  // ── Styles ──────────────────────────────────────────────────────────────────
  const overlay = {
    position: 'fixed', inset: 0, zIndex: 1000,
    backgroundColor: 'rgba(0,0,0,0.75)',
    backdropFilter: 'blur(6px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: '1rem',
  };
  const modal = {
    backgroundColor: '#0f172a',
    border: `1px solid ${accent}55`,
    borderRadius: '16px',
    width: '100%', maxWidth: '860px',
    maxHeight: '85vh',
    display: 'flex', flexDirection: 'column',
    boxShadow: `0 0 40px ${accent}33`,
    overflow: 'hidden',
  };
  const header = {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '1.25rem 1.5rem',
    borderBottom: `1px solid ${accent}44`,
    background: `linear-gradient(135deg, #1e293b, #0f172a)`,
    flexShrink: 0,
  };
  const titleStyle = {
    fontSize: '1.35rem', fontWeight: '800', color: '#f8fafc',
    display: 'flex', alignItems: 'center', gap: '0.5rem',
  };
  const closeBtn = {
    background: 'none', border: '1px solid #334155',
    color: '#94a3b8', borderRadius: '8px',
    padding: '0.4rem 0.8rem', cursor: 'pointer', fontSize: '1rem',
    transition: 'all 0.2s',
  };
  const body = {
    overflowY: 'auto', padding: '1.25rem 1.5rem',
    display: 'flex', flexDirection: 'column', gap: '1rem',
  };
  const emptyMsg = {
    textAlign: 'center', color: '#475569', padding: '4rem 0',
    fontSize: '1rem',
  };
  const card = {
    backgroundColor: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '12px',
    display: 'grid',
    gridTemplateColumns: '120px 1fr auto',
    gap: '1rem',
    padding: '0.9rem',
    alignItems: 'center',
    transition: 'border-color 0.2s',
  };
  const thumbBox = {
    width: '100%', aspectRatio: '9/16',
    backgroundColor: '#0f172a',
    borderRadius: '8px',
    overflow: 'hidden',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    border: '1px solid #334155',
  };
  const metaArea = { display: 'flex', flexDirection: 'column', gap: '0.35rem', minWidth: 0 };
  const fileName = { fontWeight: '700', color: '#f8fafc', fontSize: '0.95rem', wordBreak: 'break-all' };
  const metaRow = { color: '#64748b', fontSize: '0.8rem' };
  const actionsArea = { display: 'flex', flexDirection: 'column', gap: '0.5rem', alignItems: 'flex-end' };
  const dlBtn = {
    padding: '0.45rem 0.9rem', backgroundColor: accent,
    color: 'white', border: 'none', borderRadius: '8px',
    fontWeight: '700', cursor: 'pointer', fontSize: '0.85rem', textDecoration: 'none',
    display: 'flex', alignItems: 'center', gap: '0.3rem', whiteSpace: 'nowrap',
  };
  const delBtn = (isDeleting) => ({
    padding: '0.45rem 0.9rem',
    backgroundColor: 'transparent',
    color: isDeleting ? '#64748b' : '#f87171',
    border: '1px solid #f8717155',
    borderRadius: '8px', fontWeight: '600', cursor: isDeleting ? 'not-allowed' : 'pointer',
    fontSize: '0.85rem', whiteSpace: 'nowrap',
    transition: 'all 0.2s',
  });

  const upBtn = (isUploading) => ({
    padding: '0.45rem 0.9rem', backgroundColor: isUploading ? '#64748b' : '#3b82f6',
    color: 'white', border: 'none', borderRadius: '8px',
    fontWeight: '700', cursor: isUploading ? 'not-allowed' : 'pointer', fontSize: '0.85rem',
    display: 'flex', alignItems: 'center', gap: '0.3rem', whiteSpace: 'nowrap',
    transition: 'all 0.2s',
  });

  return (
    <div style={overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={modal}>
        {/* Header */}
        <div style={header}>
          <span style={titleStyle}>
            🗂️ {label} History
            {!loading && <span style={{ fontSize: '0.9rem', fontWeight: '500', color: '#64748b' }}>
              ({files.length} clip{files.length !== 1 ? 's' : ''})
            </span>}
          </span>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button onClick={fetchHistory} style={{ ...closeBtn, borderColor: `${accent}55`, color: accent }} title="Refresh">
              ↻
            </button>
            <button onClick={onClose} style={closeBtn}>✕ Close</button>
          </div>
        </div>

        {/* Body */}
        <div style={body}>
          {loading && (
            <div style={emptyMsg}>⏳ Loading history…</div>
          )}
          {error && (
            <div style={{ ...emptyMsg, color: '#f87171' }}>❌ {error}</div>
          )}
          {!loading && !error && files.length === 0 && (
            <div style={emptyMsg}>
              <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📭</div>
              No {label} clips found yet.<br />
              <span style={{ fontSize: '0.85rem' }}>Generate a short to see it here.</span>
            </div>
          )}
          {!loading && files.map(file => {
            const isDel = deleting === file.name;
            const isUp = uploading === file.name;
            return (
              <div key={file.name} style={card}>
                {/* Thumbnail */}
                <div style={thumbBox}>
                  <video
                    src={file.url}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    muted
                    playsInline
                    onMouseEnter={e => e.target.play()}
                    onMouseLeave={e => { e.target.pause(); e.target.currentTime = 0; }}
                  />
                </div>

                {/* Meta */}
                <div style={metaArea}>
                  <div style={fileName}>{file.name}</div>
                  <div style={metaRow}>📅 {formatDate(file.createdAt)}</div>
                  <div style={metaRow}>💾 {formatSize(parseFloat(file.sizeMB))}</div>
                  <div style={{ marginTop: '0.4rem' }}>
                    <span style={{
                      backgroundColor: accent + '22', color: accent,
                      borderRadius: '999px', padding: '0.2rem 0.6rem',
                      fontSize: '0.75rem', fontWeight: '700',
                    }}>
                      {file.channel === 'mrbeast' ? '🎯 MrBeast' : '⛏️ Minecraft'}
                    </span>
                  </div>
                </div>

                {/* Actions */}
                <div style={actionsArea}>
                  <button
                    onClick={() => handleUpload(file)}
                    disabled={isUp}
                    style={upBtn(isUp)}
                  >
                    {isUp ? '⏳ Uploading…' : '⬆️ Upload to YT'}
                  </button>
                  <a href={file.url} download={file.name} style={dlBtn}>
                    ⬇️ Download
                  </a>
                  <button
                    onClick={() => handleDelete(file.name)}
                    disabled={isDel}
                    style={delBtn(isDel)}
                  >
                    {isDel ? '⏳ Deleting…' : '🗑️ Delete'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
