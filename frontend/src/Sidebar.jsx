// Sidebar.jsx — ported directly from UI_GEN
import React from 'react';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard',     icon: '▦' },
  { id: 'create',    label: 'Create Report', icon: '+' },
  { id: 'history',   label: 'History',       icon: '◷' },
];

export function Sidebar({ page, onNav, user, onLogout }) {
  const getInitials = (name) => {
    if (!name) return '??';
    const parts = name.split(' ');
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.substring(0, 2).toUpperCase();
  };

  return (
    <div style={{
      width: 240, minHeight: '100vh', background: '#fff', flexShrink: 0,
      boxShadow: 'rgba(34,42,53,0.08) 1px 0px 0px 0px',
      display: 'flex', flexDirection: 'column', padding: '24px 0',
    }}>
      {/* Logo */}
      <div style={{ padding: '0 20px 28px' }}>
        <span style={{ fontFamily: "'Cal Sans',sans-serif", fontWeight: 600, fontSize: 18, color: '#242424', letterSpacing: '0.2px' }}>
          FA DPA Report
        </span>
      </div>

      {/* Nav items */}
      <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 2, padding: '0 10px' }}>
        {NAV_ITEMS.map(item => {
          const active = page === item.id;
          return (
            <button key={item.id} onClick={() => onNav(item.id)} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 12px', borderRadius: 8, border: 'none', cursor: 'pointer',
              background: active ? '#242424' : 'transparent',
              color: active ? '#fff' : '#111111',
              fontFamily: 'Inter,sans-serif', fontSize: 14, fontWeight: 500,
              textAlign: 'left', transition: 'background 0.12s',
            }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.background = '#f5f5f5'; }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}
            >
              <span style={{ fontSize: 14, opacity: active ? 1 : 0.6 }}>{item.icon}</span>
              {item.label}
            </button>
          );
        })}
      </nav>

      {/* User info */}
      <div style={{ padding: '20px', marginTop: 'auto', borderTop: '1px solid #f5f5f5' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%', background: '#242424',
            color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'Inter,sans-serif', fontSize: 12, fontWeight: 600, flexShrink: 0,
          }}>{getInitials(user?.fullName)}</div>
          <div style={{ overflow: 'hidden' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#242424', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user?.fullName}</div>
            <div style={{ fontSize: 11, color: '#898989' }}>{user?.role}</div>
          </div>
        </div>
        <button 
          onClick={onLogout}
          style={{ 
            width: '100%', padding: '8px', borderRadius: 8, border: '1px solid #eee', 
            background: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', color: '#ef4444' 
          }}
          onMouseEnter={e => e.target.style.background = '#fff0f0'}
          onMouseLeave={e => e.target.style.background = '#fff'}
        >
          Sign Out
        </button>
      </div>
    </div>
  );
}
