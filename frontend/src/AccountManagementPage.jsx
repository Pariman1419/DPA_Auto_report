import React from 'react';
import { Btn, Badge, CalSans, CARD_SHADOW } from './Components.jsx';
import { apiFetch } from './api.js';

const STATUS_TABS = ['pending', 'active', 'disabled', 'deleted'];

const thStyle = {
  padding: '10px 14px', fontSize: 11, fontWeight: 600, color: '#898989',
  textTransform: 'uppercase', letterSpacing: '0.06em', textAlign: 'left',
  fontFamily: "'Cal Sans',sans-serif", whiteSpace: 'nowrap',
};
const tdStyle = { padding: '10px 12px', fontSize: 13, color: '#242424', fontFamily: 'Inter,sans-serif' };

function statusBadgeVariant(status) {
  if (status === 'active') return 'default';
  if (status === 'pending') return 'warning';
  if (status === 'disabled') return 'danger';
  if (status === 'deleted') return 'skipped';
  return 'default';
}

function fmtDate(v) {
  if (!v) return '—';
  try {
    return new Date(v).toLocaleString();
  } catch {
    return String(v);
  }
}

// ---------------------------------------------------------------------------
// Reset-link modal — URL kept only in this component's own state, cleared on
// close so the raw one-time link doesn't linger anywhere (no localStorage).
// ---------------------------------------------------------------------------
function ResetLinkModal({ resetUrl, onClose }) {
  const [copyState, setCopyState] = React.useState('idle'); // idle | copied | failed

  // navigator.clipboard.writeText requires a secure context (HTTPS or
  // localhost) -- it's unavailable when the admin UI is reached over plain
  // HTTP on a LAN IP, which is common for this app. Fall back to the older
  // execCommand('copy') via a hidden textarea, which works there too.
  const legacyCopy = (text) => {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch {
      ok = false;
    }
    document.body.removeChild(textarea);
    return ok;
  };

  const handleCopy = async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(resetUrl);
      } else if (!legacyCopy(resetUrl)) {
        throw new Error('copy unsupported');
      }
      setCopyState('copied');
    } catch {
      setCopyState('failed');
    }
    setTimeout(() => setCopyState('idle'), 1500);
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
    }} onClick={onClose}>
      <div style={{ background: '#fff', borderRadius: 12, padding: 28, maxWidth: 480, width: '100%', boxShadow: CARD_SHADOW }}
        onClick={e => e.stopPropagation()}>
        <div style={{ fontFamily: "'Cal Sans',sans-serif", fontWeight: 600, fontSize: 18, color: '#242424', marginBottom: 8 }}>
          Password reset link
        </div>
        <div style={{ fontSize: 13, color: '#898989', marginBottom: 12 }}>
          This link is shown once and expires in 30 minutes. Send it to the account holder directly — it is not emailed automatically.
        </div>
        <div style={{ fontSize: 12, fontFamily: 'monospace', color: '#242424', background: '#f5f5f5',
          borderRadius: 6, padding: '10px 12px', marginBottom: 20, wordBreak: 'break-all' }}>
          {resetUrl}
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn variant="ghost" onClick={onClose}>Close</Btn>
          <Btn variant="ghost" onClick={handleCopy}>
            {copyState === 'copied' ? 'Copied ✓' : copyState === 'failed' ? 'Copy failed' : 'Copy'}
          </Btn>
          <Btn variant="primary" onClick={() => window.open(resetUrl, '_blank')}>Open</Btn>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Permanent-delete confirmation — requires typed Employee ID match + reason.
// ---------------------------------------------------------------------------
function DeleteAccountModal({ userId, onConfirm, onCancel, deleting }) {
  const [confirmUserId, setConfirmUserId] = React.useState('');
  const [reason, setReason] = React.useState('');

  const canDelete = confirmUserId === userId && reason.trim().length > 0;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
    }} onClick={onCancel}>
      <div style={{ background: '#fff', borderRadius: 12, padding: 28, maxWidth: 440, width: '100%', boxShadow: CARD_SHADOW }}
        onClick={e => e.stopPropagation()}>
        <div style={{ fontFamily: "'Cal Sans',sans-serif", fontWeight: 600, fontSize: 18, color: '#242424', marginBottom: 8 }}>
          Permanently delete this account?
        </div>
        <div style={{ fontSize: 13, color: '#898989', marginBottom: 16 }}>
          This cannot be undone. Type the Employee ID <strong style={{ color: '#242424' }}>{userId}</strong> to confirm and give a reason.
        </div>

        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#242424', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 5 }}>
            Employee ID
          </div>
          <input
            value={confirmUserId}
            onChange={e => setConfirmUserId(e.target.value)}
            placeholder={userId}
            style={{ width: '100%', padding: '9px 12px', border: 'none', borderRadius: 8,
              boxShadow: CARD_SHADOW, fontFamily: 'monospace', fontSize: 13,
              color: '#242424', outline: 'none', boxSizing: 'border-box' }}
          />
        </div>

        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#242424', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 5 }}>
            Reason
          </div>
          <textarea
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder="Why is this account being deleted?"
            rows={3}
            style={{ width: '100%', padding: '9px 12px', border: 'none', borderRadius: 8,
              boxShadow: CARD_SHADOW, fontFamily: 'Inter,sans-serif', fontSize: 13,
              color: '#242424', outline: 'none', boxSizing: 'border-box', resize: 'vertical' }}
          />
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn variant="ghost" onClick={onCancel}>Cancel</Btn>
          <Btn variant="danger" disabled={!canDelete || deleting} onClick={() => onConfirm(confirmUserId, reason)}>
            {deleting ? 'Deleting…' : 'Delete permanently'}
          </Btn>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail panel — Activity (paged) + Performance (aggregated, date-bounded).
// Never fetches "all telemetry" — only the paged/aggregated admin endpoints.
// ---------------------------------------------------------------------------
function AccountDetailPanel({ userId, onClose }) {
  const [tab, setTab] = React.useState('activity');

  const [activityItems, setActivityItems] = React.useState([]);
  const [activityCursor, setActivityCursor] = React.useState(null);
  const [activityLoading, setActivityLoading] = React.useState(false);
  const [activityError, setActivityError] = React.useState('');

  const [perf, setPerf] = React.useState(null);
  const [perfLoading, setPerfLoading] = React.useState(false);
  const [perfError, setPerfError] = React.useState('');
  const [start, setStart] = React.useState('');
  const [end, setEnd] = React.useState('');

  const loadActivity = React.useCallback(async (cursor) => {
    setActivityLoading(true);
    setActivityError('');
    try {
      const params = new URLSearchParams({ limit: '25' });
      if (cursor) params.set('cursor', cursor);
      const res = await apiFetch(`/api/admin/accounts/${encodeURIComponent(userId)}/activity?${params}`);
      if (res.status === 403) { setActivityError('You do not have permission to view this.'); return; }
      if (!res.ok) { setActivityError('Failed to load activity.'); return; }
      const data = await res.json();
      setActivityItems(prev => cursor ? [...prev, ...(data.items || [])] : (data.items || []));
      setActivityCursor(data.next_cursor || null);
    } catch {
      setActivityError('Failed to load activity.');
    } finally {
      setActivityLoading(false);
    }
  }, [userId]);

  const loadPerformance = React.useCallback(async () => {
    setPerfLoading(true);
    setPerfError('');
    try {
      const params = new URLSearchParams();
      if (start) params.set('start', new Date(start).toISOString());
      if (end) params.set('end', new Date(end).toISOString());
      const qs = params.toString();
      const res = await apiFetch(`/api/admin/accounts/${encodeURIComponent(userId)}/performance${qs ? `?${qs}` : ''}`);
      if (res.status === 403) { setPerfError('You do not have permission to view this.'); return; }
      if (!res.ok) { setPerfError('Failed to load performance.'); return; }
      setPerf(await res.json());
    } catch {
      setPerfError('Failed to load performance.');
    } finally {
      setPerfLoading(false);
    }
  }, [userId, start, end]);

  React.useEffect(() => { loadActivity(null); }, [loadActivity]);
  React.useEffect(() => { loadPerformance(); }, [loadPerformance]);

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
    <div style={{ background: '#fff', borderRadius: 12, boxShadow: CARD_SHADOW, padding: 20, marginTop: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontFamily: "'Cal Sans',sans-serif", fontWeight: 600, fontSize: 15, color: '#242424' }}>
          Account detail — {userId}
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#898989', fontSize: 16 }}>✕</button>
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 16, background: '#f5f5f5', borderRadius: 8, padding: 4, width: 'fit-content' }}>
        {tabBtn('activity', 'Activity')}
        {tabBtn('performance', 'Performance')}
      </div>

      {tab === 'activity' && (
        <div>
          {activityError && <div style={{ fontSize: 13, color: '#ef4444', marginBottom: 12 }}>{activityError}</div>}
          {!activityError && activityItems.length === 0 && !activityLoading && (
            <div style={{ fontSize: 13, color: '#898989' }}>No activity recorded.</div>
          )}
          {activityItems.length > 0 && (
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f5f5f5' }}>
                    {['When', 'Actor', 'Action'].map(h => <th key={h} style={thStyle}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {activityItems.map(item => (
                    <tr key={item.id} style={{ borderTop: '1px solid #f5f5f5' }}>
                      <td style={{ ...tdStyle, whiteSpace: 'nowrap', color: '#898989' }}>{fmtDate(item.occurred_at)}</td>
                      <td style={tdStyle}>{item.actor_user_id || '—'}</td>
                      <td style={tdStyle}>{item.action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div style={{ marginTop: 12, display: 'flex', justifyContent: 'center' }}>
            {activityCursor && (
              <Btn variant="ghost" size="sm" onClick={() => loadActivity(activityCursor)} disabled={activityLoading}>
                {activityLoading ? 'Loading…' : 'Load more'}
              </Btn>
            )}
            {!activityCursor && activityLoading && <div style={{ fontSize: 12, color: '#898989' }}>Loading…</div>}
          </div>
        </div>
      )}

      {tab === 'performance' && (
        <div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 16, flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 11, color: '#898989', marginBottom: 4 }}>Start</div>
              <input type="datetime-local" value={start} onChange={e => setStart(e.target.value)}
                style={{ padding: '6px 10px', borderRadius: 7, border: '1px solid #eee', fontSize: 12, fontFamily: 'Inter,sans-serif' }} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#898989', marginBottom: 4 }}>End</div>
              <input type="datetime-local" value={end} onChange={e => setEnd(e.target.value)}
                style={{ padding: '6px 10px', borderRadius: 7, border: '1px solid #eee', fontSize: 12, fontFamily: 'Inter,sans-serif' }} />
            </div>
            <Btn variant="ghost" size="sm" onClick={loadPerformance} disabled={perfLoading}>
              {perfLoading ? 'Loading…' : 'Apply'}
            </Btn>
          </div>

          {perfError && <div style={{ fontSize: 13, color: '#ef4444' }}>{perfError}</div>}

          {!perfError && perf && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
              {[
                ['Requests', perf.request_count],
                ['Errors', perf.error_count],
                ['Avg latency (ms)', perf.avg_duration_ms != null ? Math.round(perf.avg_duration_ms) : '—'],
                ['Max latency (ms)', perf.max_duration_ms != null ? Math.round(perf.max_duration_ms) : '—'],
              ].map(([label, val]) => (
                <div key={label} style={{ background: '#f5f5f5', borderRadius: 8, padding: '12px 14px' }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: '#898989', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
                  <div style={{ fontFamily: "'Cal Sans',sans-serif", fontSize: 22, fontWeight: 600, color: '#242424' }}>{val}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export function AccountManagementPage() {
  const [status, setStatus] = React.useState('pending');
  const [searchInput, setSearchInput] = React.useState('');
  const [search, setSearch] = React.useState('');

  const [accounts, setAccounts] = React.useState([]);
  const [nextCursor, setNextCursor] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');
  const [forbidden, setForbidden] = React.useState(false);

  const [busyRow, setBusyRow] = React.useState(null); // `${user_id}:${action}`
  const [resetModal, setResetModal] = React.useState(null); // { resetUrl } | null
  const [deleteModal, setDeleteModal] = React.useState(null); // userId | null
  const [deleting, setDeleting] = React.useState(false);
  const [expandedRow, setExpandedRow] = React.useState(null);

  // Debounce search input -> search query param.
  React.useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  const loadAccounts = React.useCallback(async (cursor) => {
    setLoading(!cursor);
    setError('');
    try {
      const params = new URLSearchParams({ status, limit: '50' });
      if (search) params.set('search', search);
      if (cursor) params.set('cursor', cursor);
      const res = await apiFetch(`/api/admin/accounts?${params}`);
      if (res.status === 403) {
        setForbidden(true);
        setAccounts([]);
        return;
      }
      setForbidden(false);
      if (!res.ok) { setError('Failed to load accounts.'); return; }
      const data = await res.json();
      setAccounts(prev => cursor ? [...prev, ...(data.items || [])] : (data.items || []));
      setNextCursor(data.next_cursor || null);
    } catch {
      setError('Failed to load accounts.');
    } finally {
      setLoading(false);
    }
  }, [status, search]);

  React.useEffect(() => {
    setExpandedRow(null);
    loadAccounts(null);
  }, [loadAccounts]);

  const runAction = async (userId, action) => {
    setBusyRow(`${userId}:${action}`);
    try {
      const res = await apiFetch(`/api/admin/accounts/${encodeURIComponent(userId)}/${action}`, { method: 'POST' });
      if (res.status === 403) { alert('You do not have permission to perform this action.'); return; }
      if (!res.ok) {
        let detail = 'Action failed.';
        try { detail = (await res.json()).detail || detail; } catch { /* non-JSON body */ }
        alert(detail);
        return;
      }
      if (action === 'reset-link') {
        const data = await res.json();
        setResetModal({ resetUrl: data.resetUrl });
      } else {
        // approve / disable / restore change the account's status -- it
        // drops off the current tab, so just remove it from the list.
        setAccounts(prev => prev.filter(a => a.user_id !== userId));
      }
    } catch {
      alert('Action failed.');
    } finally {
      setBusyRow(null);
    }
  };

  const handleDeleteConfirm = async (confirmUserId, reason) => {
    const userId = deleteModal;
    setDeleting(true);
    try {
      const res = await apiFetch(`/api/admin/accounts/${encodeURIComponent(userId)}`, {
        method: 'DELETE',
        body: JSON.stringify({ confirmUserId, reason }),
      });
      if (res.status === 403) { alert('You do not have permission to perform this action.'); return; }
      if (!res.ok) {
        let detail = 'Delete failed.';
        try { detail = (await res.json()).detail || detail; } catch { /* non-JSON body */ }
        alert(detail);
        return;
      }
      setAccounts(prev => prev.filter(a => a.user_id !== userId));
      setDeleteModal(null);
    } catch {
      alert('Delete failed.');
    } finally {
      setDeleting(false);
    }
  };

  const closeResetModal = () => setResetModal(null); // clears resetUrl from state

  const renderActions = (row) => {
    const disabledBusy = (action) => busyRow === `${row.user_id}:${action}`;
    if (row.account_status === 'pending') {
      return (
        <Btn variant="ghost" size="sm" disabled={disabledBusy('approve')} onClick={() => runAction(row.user_id, 'approve')}>
          {disabledBusy('approve') ? 'Approving…' : 'Approve'}
        </Btn>
      );
    }
    if (row.account_status === 'active') {
      return (
        <div style={{ display: 'flex', gap: 6 }}>
          <Btn variant="ghost" size="sm" disabled={disabledBusy('disable')} onClick={() => runAction(row.user_id, 'disable')}>
            {disabledBusy('disable') ? 'Disabling…' : 'Disable'}
          </Btn>
          <Btn variant="ghost" size="sm" disabled={disabledBusy('reset-link')} onClick={() => runAction(row.user_id, 'reset-link')}>
            {disabledBusy('reset-link') ? 'Generating…' : 'Reset Password'}
          </Btn>
        </div>
      );
    }
    if (row.account_status === 'disabled') {
      return (
        <div style={{ display: 'flex', gap: 6 }}>
          <Btn variant="ghost" size="sm" disabled={disabledBusy('restore')} onClick={() => runAction(row.user_id, 'restore')}>
            {disabledBusy('restore') ? 'Restoring…' : 'Restore'}
          </Btn>
          <Btn variant="danger" size="sm" onClick={() => setDeleteModal(row.user_id)}>Delete permanently</Btn>
        </div>
      );
    }
    // deleted -- no actions
    return <span style={{ fontSize: 12, color: '#898989' }}>—</span>;
  };

  if (forbidden) {
    return (
      <div>
        <CalSans size={32} style={{ display: 'block', marginBottom: 12 }}>Account Management</CalSans>
        <div style={{ fontSize: 14, color: '#ef4444' }}>
          You do not have permission to view this page. Admin access is required.
        </div>
      </div>
    );
  }

  return (
    <div>
      <CalSans size={32} style={{ display: 'block', marginBottom: 12 }}>Account Management</CalSans>
      <div style={{ fontSize: 14, color: '#898989', marginBottom: 24 }}>Approve, disable, restore, and audit user accounts.</div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 20, background: '#f5f5f5', borderRadius: 8, padding: 4, width: 'fit-content' }}>
        {STATUS_TABS.map(s => (
          <button key={s} onClick={() => setStatus(s)}
            style={{
              padding: '7px 16px', borderRadius: 7, border: 'none', cursor: 'pointer',
              background: status === s ? '#242424' : 'transparent',
              color: status === s ? '#fff' : '#898989',
              fontFamily: 'Inter,sans-serif', fontSize: 13, fontWeight: 600, textTransform: 'capitalize',
            }}>
            {s}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ flex: '1', minWidth: 200, maxWidth: 320 }}>
          <input
            placeholder="Search name, ID, or email…"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            style={{ width: '100%', padding: '8px 12px', border: 'none', borderRadius: 8,
              boxShadow: CARD_SHADOW, fontFamily: 'Inter,sans-serif', fontSize: 13,
              color: '#242424', outline: 'none', boxSizing: 'border-box' }}
          />
        </div>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: '#898989' }}>
          {loading ? 'Loading…' : `${accounts.length} account${accounts.length !== 1 ? 's' : ''}`}
        </div>
      </div>

      <div style={{ background: '#fff', borderRadius: 12, boxShadow: CARD_SHADOW, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              {['Employee ID', 'Name', 'Email', 'Role', 'Status', 'Created', 'Actions'].map(h => (
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
            {!loading && !error && accounts.map(row => (
              <React.Fragment key={row.user_id}>
                <tr
                  onClick={() => setExpandedRow(prev => prev === row.user_id ? null : row.user_id)}
                  style={{ background: expandedRow === row.user_id ? '#f9f9f9' : '#fff', cursor: 'pointer', borderTop: '1px solid rgba(34,42,53,0.05)' }}
                >
                  <td style={{ ...tdStyle, fontWeight: 600, fontFamily: 'monospace' }}>{row.user_id}</td>
                  <td style={tdStyle}>{row.full_name}</td>
                  <td style={{ ...tdStyle, color: '#898989' }}>{row.email || '—'}</td>
                  <td style={tdStyle}>{row.role}</td>
                  <td style={tdStyle}><Badge variant={statusBadgeVariant(row.account_status)}>{row.account_status}</Badge></td>
                  <td style={{ ...tdStyle, color: '#898989', whiteSpace: 'nowrap' }}>{fmtDate(row.created_at)}</td>
                  <td style={{ ...tdStyle, padding: '8px 12px' }} onClick={e => e.stopPropagation()}>
                    {renderActions(row)}
                  </td>
                </tr>
                {expandedRow === row.user_id && (
                  <tr>
                    <td colSpan={7} style={{ padding: '0 14px 14px' }}>
                      <AccountDetailPanel userId={row.user_id} onClose={() => setExpandedRow(null)} />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
            {!loading && !error && accounts.length === 0 && (
              <tr>
                <td colSpan={7} style={{ ...tdStyle, textAlign: 'center', color: '#898989', padding: '40px 14px' }}>
                  {search ? 'No accounts match this search.' : `No ${status} accounts.`}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {nextCursor && !loading && (
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
          <Btn variant="ghost" onClick={() => loadAccounts(nextCursor)}>Load more</Btn>
        </div>
      )}

      {resetModal && (
        <ResetLinkModal resetUrl={resetModal.resetUrl} onClose={closeResetModal} />
      )}

      {deleteModal && (
        <DeleteAccountModal
          userId={deleteModal}
          deleting={deleting}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteModal(null)}
        />
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default AccountManagementPage;
