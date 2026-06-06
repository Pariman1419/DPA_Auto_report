// ErrorStates.jsx — UI prototype / demo component (not used in production flow)
import React from 'react';
import { Btn, CalSans } from './Components.jsx';

const CARD_SHADOW = 'rgba(19,19,22,0.7) 0px 1px 5px -4px, rgba(34,42,53,0.08) 0px 0px 0px 1px, rgba(34,42,53,0.05) 0px 4px 8px 0px';

function ErrorCard({ type, onClose }) {
  const configs = {
    error: {
      ring: 'rgba(239,68,68,0.3) 0px 0px 0px 1px',
      iconColor: '#ef4444', iconLabel: '✗',
      title: 'NAS Folder Not Found',
      body: <><span>Path: </span><code style={{ fontFamily: 'monospace', fontSize: 12, background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>\\th1srnas6\FALab_DataSharing\PR2024001\T0\MTDQS0906.1\</code></>,
      actions: [['Retry', 'ghost'], ['Change Path Manually', 'ghost']],
    },
    warning: {
      ring: 'rgba(180,83,9,0.2) 0px 0px 0px 1px',
      iconColor: '#b45309', iconLabel: '⚠',
      title: 'Database Connection Failed',
      body: 'PACKAGE_CODE could not be retrieved. Enter manually:',
      input: true,
      actions: [['Continue Anyway', 'primary'], ['Cancel', 'ghost']],
    },
    info: {
      ring: 'rgba(34,42,53,0.08) 0px 0px 0px 1px',
      iconColor: '#898989', iconLabel: '○',
      title: 'Folder 4.DECAP is Empty',
      body: 'This slide will be skipped in the final report.',
      actions: [['OK, Continue', 'primary'], ['Cancel', 'ghost']],
    },
  };

  const c = configs[type];
  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: 28, maxWidth: 440, width: '100%',
      boxShadow: `rgba(19,19,22,0.7) 0px 1px 5px -4px, ${c.ring}, rgba(34,42,53,0.05) 0px 4px 8px 0px` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <div style={{ fontSize: 16, color: c.iconColor, fontWeight: 700 }}>{c.iconLabel}</div>
        <CalSans size={16}>{c.title}</CalSans>
      </div>
      <div style={{ fontSize: 13, color: '#898989', lineHeight: 1.6, marginBottom: c.input ? 14 : 20 }}>{c.body}</div>
      {c.input && (
        <input placeholder="e.g. NQC500E500X032U"
          style={{ width: '100%', padding: '9px 12px', marginBottom: 20, border: 'none', borderRadius: 8, outline: 'none',
            fontFamily: 'Inter,sans-serif', fontSize: 14, color: '#242424', boxShadow: CARD_SHADOW }} />
      )}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        {c.actions.map(([label, variant]) => (
          <Btn key={label} variant={variant} size="sm" onClick={onClose}>{label}</Btn>
        ))}
      </div>
    </div>
  );
}

export function ErrorStatesDemo({ onClose }) {
  const [active, setActive] = React.useState(null);
  const demos = [
    { type: 'error',   label: 'NAS Not Found',         color: '#ef4444' },
    { type: 'warning', label: 'DB Connection Failed',   color: '#b45309' },
    { type: 'info',    label: 'Empty Folder',           color: '#898989' },
  ];
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.18)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 50, flexDirection: 'column', gap: 16, padding: 24 }}>
      {!active && (
        <div style={{ background: '#fff', borderRadius: 12, padding: 28, maxWidth: 380, width: '100%', boxShadow: CARD_SHADOW }}>
          <CalSans size={16} style={{ display: 'block', marginBottom: 4 }}>Error & Warning States</CalSans>
          <div style={{ fontSize: 13, color: '#898989', marginBottom: 20 }}>Select a state to preview:</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
            {demos.map(d => (
              <button key={d.type} onClick={() => setActive(d.type)}
                style={{ padding: '10px 14px', border: 'none', borderRadius: 8, cursor: 'pointer', textAlign: 'left',
                  fontFamily: 'Inter,sans-serif', fontSize: 13, fontWeight: 500, color: d.color,
                  boxShadow: CARD_SHADOW, background: '#fff' }}>
                {d.label}
              </button>
            ))}
          </div>
          <Btn variant="ghost" size="sm" onClick={onClose}>Close</Btn>
        </div>
      )}
      {active && (
        <div onClick={() => setActive(null)}>
          <div onClick={e => e.stopPropagation()}>
            <ErrorCard type={active} onClose={() => setActive(null)} />
          </div>
        </div>
      )}
    </div>
  );
}
