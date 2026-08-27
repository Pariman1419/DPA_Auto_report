import React from 'react';
import { Btn, CalSans, CARD_SHADOW } from './Components.jsx';
import { apiFetch } from './api.js';

const thStyle = {
  padding: '10px 14px', fontSize: 11, fontWeight: 600, color: '#898989',
  textTransform: 'uppercase', letterSpacing: '0.06em', textAlign: 'left',
  fontFamily: "'Cal Sans',sans-serif", whiteSpace: 'nowrap',
};
const tdStyle = { padding: '10px 12px', fontSize: 13, color: '#242424', fontFamily: 'Inter,sans-serif' };

function fmtDate(v) {
  if (!v) return '—';
  try {
    return new Date(v).toLocaleString();
  } catch {
    return String(v);
  }
}

function sessionStatus(row) {
  if (row.revoked_at) return { label: 'Revoked', color: '#ef4444' };
  if (row.logged_out_at) return { label: 'Logged out', color: '#898989' };
  if (row.expires_at && new Date(row.expires_at) < new Date()) return { label: 'Expired', color: '#898989' };
  return { label: 'Active', color: '#22c55e' };
}

// ---------------------------------------------------------------------------
// Sessions tab — paged login-session history across all accounts, optionally
// filtered to one user_id. Read-only (session revocation itself already
// happens elsewhere, e.g. a password reset bumping session_version).
// ---------------------------------------------------------------------------
function SessionsTab() {
  const [userIdFilter, setUserIdFilter] = React.useState('');
  const [items, setItems] = React.useState([]);
  const [cursor, setCursor] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');

  const load = React.useCallback(async (nextCursor) => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ limit: '25' });
      if (userIdFilter.trim()) params.set('user_id', userIdFilter.trim());
      if (nextCursor) params.set('cursor', nextCursor);
      const res = await apiFetch(`/api/admin/sessions?${params}`);
      if (res.status === 403) { setError('You do not have permission to view this.'); return; }
      if (!res.ok) { setError('Failed to load sessions.'); return; }
      const data = await res.json();
      setItems(prev => nextCursor ? [...prev, ...(data.items || [])] : (data.items || []));
      setCursor(data.next_cursor || null);
    } catch {
      setError('Failed to load sessions.');
    } finally {
      setLoading(false);
    }
  }, [userIdFilter]);

  React.useEffect(() => { load(null); }, [load]);

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, color: '#898989', marginBottom: 4 }}>Filter by Employee ID</div>
          <input
            value={userIdFilter}
            onChange={e => setUserIdFilter(e.target.value)}
            placeholder="e.g. EMP001"
            style={{ padding: '6px 10px', borderRadius: 7, border: '1px solid #eee', fontSize: 12, fontFamily: 'Inter,sans-serif', width: 180 }}
          />
        </div>
        <Btn variant="ghost" size="sm" onClick={() => load(null)} disabled={loading}>
          {loading ? 'Loading…' : 'Apply'}
        </Btn>
      </div>

      {error && <div style={{ fontSize: 13, color: '#ef4444', marginBottom: 12 }}>{error}</div>}
      {!error && items.length === 0 && !loading && (
        <div style={{ fontSize: 13, color: '#898989' }}>No sessions recorded.</div>
      )}
      {items.length > 0 && (
        <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f5f5f5' }}>
                {['Started', 'User', 'IP address', 'Last seen', 'Status'].map(h => <th key={h} style={thStyle}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {items.map(row => {
                const status = sessionStatus(row);
                return (
                  <tr key={row.id} style={{ borderTop: '1px solid #f5f5f5' }}>
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap', color: '#898989' }}>{fmtDate(row.started_at)}</td>
                    <td style={tdStyle}>{row.user_id}</td>
                    <td style={tdStyle}>{row.ip_address || '—'}</td>
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap', color: '#898989' }}>{fmtDate(row.last_seen_at)}</td>
                    <td style={tdStyle}><span style={{ color: status.color, fontWeight: 600 }}>{status.label}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ marginTop: 12, display: 'flex', justifyContent: 'center' }}>
        {cursor && (
          <Btn variant="ghost" size="sm" onClick={() => load(cursor)} disabled={loading}>
            {loading ? 'Loading…' : 'Load more'}
          </Btn>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Daily Performance tab — pre-aggregated per-route rollup from
// endpoint_latency_daily. That table only fills in once the scheduled
// rollup job runs, so an empty result here is explained, not hidden.
// ---------------------------------------------------------------------------
function DailyPerformanceTab() {
  const [days, setDays] = React.useState('30');
  const [routeFilter, setRouteFilter] = React.useState('');
  const [items, setItems] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');

  const load = React.useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ days });
      if (routeFilter.trim()) params.set('route', routeFilter.trim());
      const res = await apiFetch(`/api/admin/performance/daily?${params}`);
      if (res.status === 403) { setError('You do not have permission to view this.'); return; }
      if (!res.ok) { setError('Failed to load performance data.'); return; }
      const data = await res.json();
      setItems(data.items || []);
    } catch {
      setError('Failed to load performance data.');
    } finally {
      setLoading(false);
    }
  }, [days, routeFilter]);

  React.useEffect(() => { load(); }, [load]);

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 11, color: '#898989', marginBottom: 4 }}>Range</div>
          <select value={days} onChange={e => setDays(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: 7, border: '1px solid #eee', fontSize: 12, fontFamily: 'Inter,sans-serif' }}>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
          </select>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#898989', marginBottom: 4 }}>Filter by route</div>
          <input
            value={routeFilter}
            onChange={e => setRouteFilter(e.target.value)}
            placeholder="e.g. /api/product-requests"
            style={{ padding: '6px 10px', borderRadius: 7, border: '1px solid #eee', fontSize: 12, fontFamily: 'Inter,sans-serif', width: 220 }}
          />
        </div>
        <Btn variant="ghost" size="sm" onClick={load} disabled={loading}>
          {loading ? 'Loading…' : 'Apply'}
        </Btn>
      </div>

      {error && <div style={{ fontSize: 13, color: '#ef4444', marginBottom: 12 }}>{error}</div>}
      {!error && items.length === 0 && !loading && (
        <div style={{ fontSize: 13, color: '#898989' }}>
          No data for this range. This view reads a daily rollup that only fills in once the
          scheduled rollup job has run — it does not mean there was no traffic.
        </div>
      )}
      {items.length > 0 && (
        <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f5f5f5' }}>
                {['Day', 'Route', 'Requests', 'Errors', 'Avg (ms)', 'P95 (ms)', 'Max (ms)'].map(h => <th key={h} style={thStyle}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {items.map((row, i) => (
                <tr key={`${row.route}-${row.day}-${i}`} style={{ borderTop: '1px solid #f5f5f5' }}>
                  <td style={{ ...tdStyle, whiteSpace: 'nowrap', color: '#898989' }}>{row.day}</td>
                  <td style={tdStyle}>{row.route}</td>
                  <td style={tdStyle}>{row.request_count}</td>
                  <td style={tdStyle}>{row.error_count}</td>
                  <td style={tdStyle}>{row.avg_latency_ms != null ? Math.round(row.avg_latency_ms) : '—'}</td>
                  <td style={tdStyle}>{row.p95_latency_ms != null ? Math.round(row.p95_latency_ms) : '—'}</td>
                  <td style={tdStyle}>{row.max_latency_ms != null ? Math.round(row.max_latency_ms) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function SystemMonitoringPage() {
  const [tab, setTab] = React.useState('sessions');

  const tabBtn = (id, label) => (
    <button
      onClick={() => setTab(id)}
      style={{
        padding: '6px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
        background: tab === id ? '#242424' : 'transparent',
        color: tab === id ? '#fff' : '#898989',
        fontFamily: 'Inter,sans-serif', fontSize: 12, fontWeight: 600,
      }}>
      {label}
    </button>
  );

  return (
    <div>
      <CalSans size={32} style={{ display: 'block', marginBottom: 12 }}>System Monitoring</CalSans>
      <div style={{ fontSize: 14, color: '#898989', marginBottom: 24 }}>
        Login sessions and per-route latency across all accounts.
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 20, background: '#f5f5f5', borderRadius: 8, padding: 4, width: 'fit-content' }}>
        {tabBtn('sessions', 'Sessions')}
        {tabBtn('performance', 'Daily Performance')}
      </div>

      <div style={{ background: '#fff', borderRadius: 12, boxShadow: CARD_SHADOW, padding: 20 }}>
        {tab === 'sessions' && <SessionsTab />}
        {tab === 'performance' && <DailyPerformanceTab />}
      </div>
    </div>
  );
}

export default SystemMonitoringPage;
