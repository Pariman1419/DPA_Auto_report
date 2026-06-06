import React from 'react';
import { Btn, Badge, CalSans } from './Components.jsx';
import { apiFetch } from './api.js';

const CARD_SHADOW = 'rgba(19,19,22,0.7) 0px 1px 5px -4px, rgba(34,42,53,0.08) 0px 0px 0px 1px, rgba(34,42,53,0.05) 0px 4px 8px 0px';

function ConfirmModal({ row, onConfirm, onCancel }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
    }}>
      <div style={{ background: '#fff', borderRadius: 12, padding: 28, maxWidth: 400, width: '100%', boxShadow: CARD_SHADOW }}>
        <div style={{ fontFamily: "'Cal Sans',sans-serif", fontWeight: 600, fontSize: 18, color: '#242424', marginBottom: 8 }}>
          Delete this report?
        </div>
        <div style={{ fontSize: 13, color: '#898989', marginBottom: 4 }}>
          This will permanently delete the record and the PPTX file from disk.
        </div>
        <div style={{ fontSize: 13, fontFamily: 'monospace', color: '#242424', background: '#f5f5f5',
          borderRadius: 6, padding: '6px 10px', marginBottom: 20, wordBreak: 'break-all' }}>
          {row.fileName}
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn variant="ghost" onClick={onCancel}>Cancel</Btn>
          <Btn variant="danger" onClick={onConfirm}>Delete permanently</Btn>
        </div>
      </div>
    </div>
  );
}

export function HistoryPage() {
  const [history, setHistory] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');
  const [search, setSearch] = React.useState('');
  const [hoveredRow, setHoveredRow] = React.useState(null);
  const [confirmRow, setConfirmRow] = React.useState(null);
  const [downloading, setDownloading] = React.useState(null);
  const [deleting, setDeleting] = React.useState(null);

  const loadHistory = () => {
    setLoading(true);
    apiFetch('/api/history')
      .then(r => r.json())
      .then(data => { setHistory(data); setLoading(false); })
      .catch(() => { setError('Failed to load history'); setLoading(false); });
  };

  React.useEffect(() => { loadHistory(); }, []);

  const handleDownload = async (row) => {
    setDownloading(row.id);
    try {
      const res = await apiFetch(`/api/history/${row.id}/download`);
      if (!res.ok) { alert('File not found on disk.'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = row.fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      alert('Download failed.');
    } finally {
      setDownloading(null);
    }
  };

  const handleDeleteConfirm = async () => {
    const row = confirmRow;
    setConfirmRow(null);
    setDeleting(row.id);
    try {
      const res = await apiFetch(`/api/history/${row.id}`, { method: 'DELETE' });
      if (res.ok) {
        setHistory(prev => prev.filter(r => r.id !== row.id));
      } else {
        alert('Delete failed.');
      }
    } catch {
      alert('Delete failed.');
    } finally {
      setDeleting(null);
    }
  };

  const filtered = history.filter(r =>
    search === '' ||
    r.prNo.toLowerCase().includes(search.toLowerCase()) ||
    (r.lot || '').toLowerCase().includes(search.toLowerCase()) ||
    (r.userName || '').toLowerCase().includes(search.toLowerCase())
  );

  const thStyle = {
    padding: '10px 14px', fontSize: 11, fontWeight: 600, color: '#898989',
    textTransform: 'uppercase', letterSpacing: '0.06em', textAlign: 'left',
    fontFamily: "'Cal Sans',sans-serif", whiteSpace: 'nowrap',
  };
  const tdStyle = { padding: '10px 12px', fontSize: 13, color: '#242424', fontFamily: 'Inter,sans-serif' };

  return (
    <div>
      <CalSans size={32} style={{ display: 'block', marginBottom: 24 }}>Report History</CalSans>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ flex: '1', minWidth: 200, maxWidth: 320 }}>
          <input
            placeholder="Search PR No., LOT or user…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ width: '100%', padding: '8px 12px', border: 'none', borderRadius: 8,
              boxShadow: CARD_SHADOW, fontFamily: 'Inter,sans-serif', fontSize: 13,
              color: '#242424', outline: 'none', boxSizing: 'border-box' }}
          />
        </div>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: '#898989' }}>
          {loading ? 'Loading…' : `${filtered.length} report${filtered.length !== 1 ? 's' : ''}`}
        </div>
      </div>

      <div style={{ background: '#fff', borderRadius: 12, boxShadow: CARD_SHADOW, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              {['PR No.', 'Stress test', 'LOT', 'Rev.', 'Created By', 'Date', 'Actions'].map(h => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} style={{ ...tdStyle, textAlign: 'center', color: '#898989', padding: '40px 14px' }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 14, height: 14, border: '2px solid #e0e0e0', borderTopColor: '#242424',
                      borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
                    Loading…
                  </div>
                </td>
              </tr>
            )}
            {!loading && error && (
              <tr>
                <td colSpan={7} style={{ ...tdStyle, textAlign: 'center', color: '#ef4444', padding: '32px 14px' }}>{error}</td>
              </tr>
            )}
            {!loading && !error && filtered.map((row, i) => {
              const isDownloading = downloading === row.id;
              const isDeleting = deleting === row.id;
              const busy = isDownloading || isDeleting;
              return (
                <tr key={row.id}
                  onMouseEnter={() => setHoveredRow(i)}
                  onMouseLeave={() => setHoveredRow(null)}
                  style={{ background: hoveredRow === i ? '#f9f9f9' : '#fff', transition: 'background 0.1s', borderTop: '1px solid rgba(34,42,53,0.05)' }}>
                  <td style={{ ...tdStyle, fontWeight: 600 }}>{row.prNo}</td>
                  <td style={tdStyle}>{row.timepoint}</td>
                  <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 12 }}>{row.lot}</td>
                  <td style={{ ...tdStyle, fontWeight: 600, color: '#898989' }}>{row.revision}</td>
                  <td style={tdStyle}>{row.userName}</td>
                  <td style={{ ...tdStyle, color: '#898989', whiteSpace: 'nowrap' }}>{row.createdAt}</td>
                  <td style={{ ...tdStyle, padding: '8px 12px' }}>
                    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                      <button
                        onClick={() => !busy && handleDownload(row)}
                        disabled={busy}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          padding: '4px 8px', borderRadius: 7, border: 'none',
                          background: isDownloading ? '#f5f5f5' : '#fff', cursor: busy ? 'not-allowed' : 'pointer',
                          fontFamily: 'Inter,sans-serif', fontSize: 11, fontWeight: 600,
                          color: isDownloading ? '#898989' : '#242424', opacity: busy && !isDownloading ? 0.4 : 1,
                          boxShadow: CARD_SHADOW, transition: 'opacity 0.15s', whiteSpace: 'nowrap',
                        }}
                        onMouseEnter={e => { if (!busy) e.currentTarget.style.background = '#f5f5f5'; }}
                        onMouseLeave={e => { if (!busy) e.currentTarget.style.background = '#fff'; }}
                      >
                        {isDownloading
                          ? <><span style={{ fontSize: 10 }}>⏳</span> PPTX</>
                          : <><span style={{ fontSize: 11 }}>↓</span> PPTX</>
                        }
                      </button>
                      {row.excelPath && (
                        <button
                          onClick={() => window.open(`/api/download-report?path=${encodeURIComponent(row.excelPath)}`, '_blank')}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 4,
                            padding: '4px 8px', borderRadius: 7, border: 'none',
                            background: '#fff', cursor: 'pointer',
                            fontFamily: 'Inter,sans-serif', fontSize: 11, fontWeight: 600,
                            color: '#059669', boxShadow: CARD_SHADOW, transition: 'background 0.12s',
                            whiteSpace: 'nowrap',
                          }}
                          onMouseEnter={e => e.currentTarget.style.background = '#ecfdf5'}
                          onMouseLeave={e => e.currentTarget.style.background = '#fff'}
                        >
                          <span style={{ fontSize: 11 }}>📊</span> Excel
                        </button>
                      )}
                      <button
                        onClick={() => !busy && setConfirmRow(row)}
                        disabled={busy}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          padding: '4px 8px', borderRadius: 7, border: 'none',
                          background: isDeleting ? '#fff0f0' : '#fff', cursor: busy ? 'not-allowed' : 'pointer',
                          fontFamily: 'Inter,sans-serif', fontSize: 11, fontWeight: 600,
                          color: '#ef4444', opacity: busy && !isDeleting ? 0.4 : 1,
                          boxShadow: CARD_SHADOW, transition: 'opacity 0.15s', whiteSpace: 'nowrap',
                        }}
                        onMouseEnter={e => { if (!busy) e.currentTarget.style.background = '#fff0f0'; }}
                        onMouseLeave={e => { if (!busy) e.currentTarget.style.background = '#fff'; }}
                      >
                        {isDeleting
                          ? <><span style={{ fontSize: 10 }}>⏳</span> Deleting…</>
                          : <><span style={{ fontSize: 11 }}>✕</span> Delete</>
                        }
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!loading && !error && filtered.length === 0 && (
              <tr>
                <td colSpan={7} style={{ ...tdStyle, textAlign: 'center', color: '#898989', padding: '40px 14px' }}>
                  {search ? 'No reports match this search.' : 'No reports generated yet.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {confirmRow && (
        <ConfirmModal
          row={confirmRow}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setConfirmRow(null)}
        />
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
