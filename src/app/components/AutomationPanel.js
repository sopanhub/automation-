'use client';

import { useState, useEffect, useCallback } from 'react';

export default function AutomationPanel({ channel }) {
  const [urls, setUrls] = useState([]);
  const [usedUrls, setUsedUrls] = useState([]);
  const [newUrl, setNewUrl] = useState('');
  const [schedulerState, setSchedulerState] = useState(null);
  const [processRunning, setProcessRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [clipQueue, setClipQueue] = useState([]);
  const [intervalHours, setIntervalHours] = useState(5);
  const [open, setOpen] = useState(false);

  const accent = channel === 'mrbeast' ? '#ef4444' : '#22d3ee';
  const label  = channel === 'mrbeast' ? 'MrBeast' : 'Minecraft';
  const icon   = channel === 'mrbeast' ? '🎯' : '⛏️';

  const flash = (text, ms = 3000) => {
    setMsg(text);
    setTimeout(() => setMsg(''), ms);
  };

  const fetchState = useCallback(async () => {
    try {
      const [urlRes, schedRes, procRes] = await Promise.all([
        fetch(`/api/url-library?channel=${channel}`),
        fetch('/api/scheduler'),
        fetch('/api/scheduler-process'),
      ]);
      const urlData  = await urlRes.json();
      const schedData = await schedRes.json();
      const procData = await procRes.json();

      setUrls(urlData.urls || []);
      setUsedUrls(urlData.used_urls || []);
      setSchedulerState(schedData[channel] || {});
      setProcessRunning(procData.running || false);
      if (channel === 'mrbeast' && schedData.mrbeast?.clip_queue) {
        setClipQueue(schedData.mrbeast.clip_queue);
      }
    } catch (e) {
      console.error('fetchState error', e);
    }
  }, [channel]);

  useEffect(() => {
    if (open) {
      fetchState();
      const interval = setInterval(fetchState, 10000);
      return () => clearInterval(interval);
    }
  }, [open, fetchState]);

  const addUrl = async () => {
    const trimmed = newUrl.trim();
    if (!trimmed) return;
    try {
      const res = await fetch('/api/url-library', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel, url: trimmed }),
      });
      const d = await res.json();
      if (d.error) { flash('❌ ' + d.error); return; }
      setUrls(d.urls);
      setNewUrl('');
      flash('✅ URL added!');
    } catch (e) {
      flash('❌ Failed to add URL');
    }
  };

  const removeUrl = async (url) => {
    try {
      const res = await fetch('/api/url-library', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel, url }),
      });
      const d = await res.json();
      if (d.error) { flash('❌ ' + d.error); return; }
      fetchState();
      flash('🗑️ URL removed.');
    } catch (e) {
      flash('❌ Failed to remove URL');
    }
  };

  const startScheduler = async () => {
    setLoading(true);
    try {
      // Start the channel schedule
      await fetch('/api/scheduler', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start', channel, interval_hours: intervalHours }),
      });
      // Start the background process if not running
      if (!processRunning) {
        await fetch('/api/scheduler-process', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'start' }),
        });
      }
      flash(`✅ Auto-mode started! First upload in ${intervalHours}h.`, 5000);
      fetchState();
    } catch (e) {
      flash('❌ Failed to start scheduler');
    } finally {
      setLoading(false);
    }
  };

  const stopScheduler = async () => {
    setLoading(true);
    try {
      await fetch('/api/scheduler', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop', channel }),
      });
      flash('⏹️ Auto-mode stopped for ' + label + '.');
      fetchState();
    } catch (e) {
      flash('❌ Failed to stop');
    } finally {
      setLoading(false);
    }
  };

  const triggerNow = async () => {
    if (!confirm(`Run the ${label} automation right now?`)) return;
    setLoading(true);
    try {
      await fetch('/api/scheduler', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'trigger_now', channel }),
      });
      if (!processRunning) {
        await fetch('/api/scheduler-process', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'start' }),
        });
      }
      flash('🚀 Triggered! Check scheduler.log for progress.', 6000);
      fetchState();
    } catch (e) {
      flash('❌ Failed to trigger');
    } finally {
      setLoading(false);
    }
  };

  const isActive = schedulerState?.is_running;
  const nextRun  = schedulerState?.next_run_label || 'Not scheduled';

  // ── Styles ────────────────────────────────────────────────────────────────
  const panelBtn = {
    padding: '0.5rem 1.1rem',
    backgroundColor: '#1e293b',
    color: accent,
    border: `1px solid ${accent}55`,
    borderRadius: '8px',
    fontWeight: '700',
    cursor: 'pointer',
    fontSize: '0.875rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
  };
  const card = {
    backgroundColor: '#1e293b',
    border: `1px solid ${accent}33`,
    borderRadius: '14px',
    padding: '1.5rem',
    marginTop: '1.5rem',
  };
  const input = {
    width: '100%',
    padding: '0.6rem 0.9rem',
    backgroundColor: '#0f172a',
    border: '1px solid #334155',
    borderRadius: '8px',
    color: '#f8fafc',
    fontSize: '0.875rem',
    boxSizing: 'border-box',
  };
  const addBtn = {
    padding: '0.6rem 1.2rem',
    backgroundColor: accent,
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontWeight: '700',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    fontSize: '0.875rem',
  };
  const tag = (used) => ({
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    padding: '0.45rem 0.75rem',
    backgroundColor: used ? '#1e293b' : '#0f172a',
    border: `1px solid ${used ? '#334155' : accent + '44'}`,
    borderRadius: '8px',
    fontSize: '0.8rem',
    color: used ? '#64748b' : '#f8fafc',
  });
  const statusDot = (on) => ({
    width: '10px', height: '10px', borderRadius: '50%',
    backgroundColor: on ? '#22c55e' : '#64748b',
    boxShadow: on ? '0 0 8px #22c55e88' : 'none',
    flexShrink: 0,
    display: 'inline-block',
  });

  return (
    <div>
      {/* Toggle Button */}
      <button onClick={() => setOpen(p => !p)} style={panelBtn}>
        🤖 Auto Mode {open ? '▲' : '▼'}
      </button>

      {open && (
        <div style={card}>
          <h3 style={{ color: accent, fontWeight: '800', margin: '0 0 1rem', fontSize: '1.1rem' }}>
            {icon} {label} Auto-Upload
          </h3>

          {msg && (
            <div style={{ padding: '0.6rem 1rem', backgroundColor: '#0f172a', borderRadius: '8px', color: '#f8fafc', fontSize: '0.85rem', marginBottom: '1rem', border: `1px solid ${accent}44` }}>
              {msg}
            </div>
          )}

          {/* Status bar */}
          <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center', padding: '0.75rem 1rem', backgroundColor: '#0f172a', borderRadius: '8px', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: '#f8fafc' }}>
              <span style={statusDot(isActive)} />
              {isActive ? <strong style={{ color: '#22c55e' }}>Active</strong> : <span style={{ color: '#64748b' }}>Idle</span>}
            </span>
            <span style={{ fontSize: '0.82rem', color: '#64748b' }}>⏰ Next upload: <strong style={{ color: '#f8fafc' }}>{nextRun}</strong></span>
            <span style={{ fontSize: '0.82rem', color: '#64748b' }}>🔄 Process: <strong style={{ color: processRunning ? '#22c55e' : '#64748b' }}>{processRunning ? 'Running' : 'Stopped'}</strong></span>
            {channel === 'mrbeast' && (
              <span style={{ fontSize: '0.82rem', color: '#64748b' }}>📦 Queue: <strong style={{ color: '#f8fafc' }}>{clipQueue.filter(c => !c.uploaded).length} pending</strong></span>
            )}
          </div>

          {/* Controls */}
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.25rem', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.82rem', color: '#94a3b8' }}>Interval:</span>
              <select
                value={intervalHours}
                onChange={e => setIntervalHours(Number(e.target.value))}
                style={{ ...input, width: 'auto', padding: '0.4rem 0.6rem' }}
              >
                <option value={1}>1 hour</option>
                <option value={2}>2 hours</option>
                <option value={3}>3 hours</option>
                <option value={5}>5 hours</option>
                <option value={8}>8 hours</option>
                <option value={12}>12 hours</option>
                <option value={24}>24 hours</option>
              </select>
            </div>
            {!isActive ? (
              <button onClick={startScheduler} disabled={loading || urls.length === 0} style={{ ...addBtn, opacity: urls.length === 0 ? 0.5 : 1 }}>
                ▶ Start Auto-Mode
              </button>
            ) : (
              <button onClick={stopScheduler} disabled={loading} style={{ ...addBtn, backgroundColor: '#334155' }}>
                ⏹ Stop
              </button>
            )}
            <button onClick={triggerNow} disabled={loading || (urls.length === 0 && (channel !== 'mrbeast' || clipQueue.filter(c => !c.uploaded).length === 0))} style={{ ...panelBtn, fontSize: '0.8rem' }}>
              🚀 Run Now
            </button>
            <button onClick={fetchState} style={{ ...panelBtn, fontSize: '0.8rem' }}>↻ Refresh</button>
          </div>

          {urls.length === 0 && usedUrls.length === 0 && (
            <p style={{ color: '#ef4444', fontSize: '0.82rem', marginBottom: '1rem' }}>
              ⚠️ Add at least one source URL to enable auto-mode.
            </p>
          )}

          {/* URL Input */}
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            <input
              type="url"
              value={newUrl}
              onChange={e => setNewUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addUrl()}
              placeholder="Paste YouTube URL and press Enter or Add…"
              style={input}
            />
            <button onClick={addUrl} style={addBtn}>+ Add</button>
          </div>

          {/* URL Library */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', maxHeight: '220px', overflowY: 'auto' }}>
            {urls.map(url => (
              <div key={url} style={tag(false)}>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{url}</span>
                <span style={{ padding: '0.15rem 0.5rem', backgroundColor: accent + '22', color: accent, borderRadius: '999px', fontSize: '0.7rem', fontWeight: '700', flexShrink: 0 }}>Queued</span>
                <button onClick={() => removeUrl(url)} style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', padding: '0', fontSize: '1rem', flexShrink: 0 }}>✕</button>
              </div>
            ))}
            {usedUrls.map(url => (
              <div key={url} style={tag(true)}>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{url}</span>
                <span style={{ padding: '0.15rem 0.5rem', backgroundColor: '#334155', color: '#64748b', borderRadius: '999px', fontSize: '0.7rem', fontWeight: '700', flexShrink: 0 }}>Used</span>
                <button onClick={() => removeUrl(url)} style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', padding: '0', fontSize: '1rem', flexShrink: 0 }}>✕</button>
              </div>
            ))}
            {urls.length === 0 && usedUrls.length === 0 && (
              <p style={{ color: '#475569', fontSize: '0.82rem', textAlign: 'center', padding: '1rem 0' }}>No URLs added yet.</p>
            )}
          </div>

          {/* MrBeast Clip Queue */}
          {channel === 'mrbeast' && clipQueue.length > 0 && (
            <div style={{ marginTop: '1.25rem' }}>
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', fontWeight: '700', marginBottom: '0.5rem' }}>📦 Clip Upload Queue</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', maxHeight: '180px', overflowY: 'auto' }}>
                {clipQueue.map((clip, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.4rem 0.75rem', backgroundColor: '#0f172a', borderRadius: '8px', border: `1px solid ${clip.uploaded ? '#334155' : accent + '44'}` }}>
                    <span style={{ fontSize: '0.75rem', color: clip.uploaded ? '#22c55e' : '#94a3b8', flexShrink: 0 }}>{clip.uploaded ? '✅' : '⏳'}</span>
                    <span style={{ flex: 1, fontSize: '0.78rem', color: clip.uploaded ? '#64748b' : '#f8fafc', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{clip.title || clip.file}</span>
                    <span style={{ fontSize: '0.72rem', color: '#475569', flexShrink: 0 }}>{clip.file}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
