// Components.jsx — Base UI primitives (ported from UI_GEN)
import React from 'react';

const CARD_SHADOW = 'rgba(19,19,22,0.7) 0px 1px 5px -4px, rgba(34,42,53,0.08) 0px 0px 0px 1px, rgba(34,42,53,0.05) 0px 4px 8px 0px';
const BTN_HIGHLIGHT = 'rgba(255,255,255,0.15) 0px 2px 0px inset';

const compStyles = {
  btn: {
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 16px',
    border: 'none', borderRadius: 8, fontFamily: 'Inter,sans-serif', fontSize: 14,
    fontWeight: 600, cursor: 'pointer', transition: 'opacity 0.15s', lineHeight: 1,
    textDecoration: 'none', whiteSpace: 'nowrap',
  },
  btnSm: { padding: '5px 10px', fontSize: 12 },
  card: {
    background: '#fff', borderRadius: 12, boxShadow: CARD_SHADOW, padding: 24,
  },
};

export function Btn({ variant = 'primary', size = 'md', onClick, children, disabled, style }) {
  const base = { ...compStyles.btn, ...(size === 'sm' ? compStyles.btnSm : {}), ...style };
  if (variant === 'primary') Object.assign(base, { background: '#242424', color: '#fff', boxShadow: BTN_HIGHLIGHT });
  if (variant === 'ghost')   Object.assign(base, { background: '#fff', color: '#242424', boxShadow: CARD_SHADOW });
  if (variant === 'danger')  Object.assign(base, { background: '#ef4444', color: '#fff' });
  if (disabled) Object.assign(base, { opacity: 0.4, cursor: 'not-allowed' });
  return (
    <button style={base} onClick={disabled ? undefined : onClick}
      onMouseEnter={e => { if (!disabled && variant === 'primary') e.target.style.opacity = '0.7'; }}
      onMouseLeave={e => { if (!disabled && variant === 'primary') e.target.style.opacity = '1'; }}>
      {children}
    </button>
  );
}

export function Badge({ variant = 'default', children }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', padding: '3px 10px',
    borderRadius: 9999, fontFamily: 'Inter,sans-serif', fontSize: 12, fontWeight: 500, lineHeight: 1.4,
  };
  if (variant === 'default')  Object.assign(base, { background: '#f5f5f5', color: '#242424' });
  if (variant === 'danger')   Object.assign(base, { background: '#fff0f0', color: '#ef4444' });
  if (variant === 'warning')  Object.assign(base, { background: '#fffbf0', color: '#b45309' });
  if (variant === 'skipped')  Object.assign(base, { background: '#f5f5f5', color: '#898989', fontStyle: 'italic' });
  return <span style={base}>{children}</span>;
}

export function FieldLabel({ children }) {
  return (
    <div style={{ fontSize: 12, fontWeight: 600, color: '#242424', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 5 }}>
      {children}
    </div>
  );
}

export function TextInput({ placeholder, value, onChange, error, style, type = 'text' }) {
  const [showPwd, setShowPwd] = React.useState(false);
  const isPassword = type === 'password';
  const inputType = isPassword ? (showPwd ? 'text' : 'password') : type;
  const shadow = error ? 'rgba(239,68,68,0.3) 0px 0px 0px 1px' : CARD_SHADOW;

  return (
    <div>
      <div style={{ position: 'relative' }}>
        <input
          type={inputType}
          style={{
            width: '100%', padding: isPassword ? '9px 40px 9px 12px' : '9px 12px',
            background: '#fff', border: 'none', borderRadius: 8,
            boxShadow: shadow, fontFamily: 'Inter,sans-serif', fontSize: 14,
            color: '#242424', outline: 'none', boxSizing: 'border-box', ...style,
          }}
          placeholder={placeholder} value={value} onChange={onChange}
        />
        {isPassword && (
          <button
            type="button"
            aria-label={showPwd ? 'Hide password' : 'Show password'}
            onClick={() => setShowPwd(p => !p)}
            style={{
              position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
              background: 'none', border: 'none', cursor: 'pointer', padding: 4,
              color: '#898989', lineHeight: 0, userSelect: 'none',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}
          >
            {showPwd ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                <line x1="1" y1="1" x2="23" y2="23"></line>
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
              </svg>
            )}
          </button>
        )}
        <style>{`
          input::-ms-reveal, input::-ms-clear { display: none; }
        `}</style>
      </div>
      {error && <div style={{ fontSize: 12, color: '#ef4444', marginTop: 4 }}>{error}</div>}
    </div>
  );
}

export function LoadingSpinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderRadius: 8, boxShadow: CARD_SHADOW, background: '#fff', justifyContent: 'center' }}>
      <div style={{ width: 16, height: 16, border: '2px solid #e0e0e0', borderTopColor: '#242424',
        borderRadius: '50%', animation: 'spin 0.7s linear infinite', flexShrink: 0 }} />
      <span style={{ fontSize: 14, color: '#898989' }}>Loading…</span>
    </div>
  );
}

export function SelectDropdown({ options, value, onChange, loading, placeholder }) {
  const [isOpen, setIsOpen] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const containerRef = React.useRef(null);

  React.useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setIsOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  React.useEffect(() => {
    if (!isOpen) setSearch('');
  }, [isOpen]);

  if (loading) return <LoadingSpinner />;

  const filteredOptions = options.filter(o => {
    const lab = typeof o === 'object' ? o.label : o;
    return String(lab).toLowerCase().includes(search.toLowerCase());
  });

  const selectedOption = options.find(o => (typeof o === 'object' ? o.value : o) === value);
  const displayLabel = selectedOption ? (typeof selectedOption === 'object' ? selectedOption.label : selectedOption) : placeholder;

  const handleSelect = (optVal) => {
    if (optVal === value) {
      onChange('');
    } else {
      onChange(optVal);
    }
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%', userSelect: 'none' }}>
      <div onClick={() => setIsOpen(!isOpen)}
        style={{ width: '100%', padding: '9px 12px', background: '#fff', borderRadius: 8,
          boxShadow: CARD_SHADOW, fontFamily: 'Inter,sans-serif', fontSize: 14, color: value ? '#242424' : '#898989',
          cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{displayLabel}</span>
        <span style={{ color: '#898989', fontSize: 11, transition: 'transform 0.2s', transform: isOpen ? 'rotate(180deg)' : 'none' }}>▾</span>
      </div>

      {isOpen && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4, background: '#fff',
          borderRadius: 8, boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05), 0 0 0 1px rgba(0,0,0,0.05)',
          zIndex: 1000, maxHeight: 300, display: 'flex', flexDirection: 'column' }}>
          
          <div style={{ padding: '8px', borderBottom: '1px solid #f0f0f0', position: 'sticky', top: 0, background: '#fff', borderRadius: '8px 8px 0 0' }}>
            <input 
              autoFocus
              placeholder="Search..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '6px 10px', fontSize: 13, border: '1px solid #e5e7eb', borderRadius: 6, outline: 'none' }}
              onClick={e => e.stopPropagation()}
            />
          </div>

          <div style={{ overflowY: 'auto', flex: 1 }}>
            {filteredOptions.length > 0 ? filteredOptions.map((o, i) => {
              const optVal = typeof o === 'object' ? o.value : o;
              const optLab = typeof o === 'object' ? o.label : o;
              const isSelected = optVal === value;
              return (
                <div key={i} onClick={() => handleSelect(optVal)}
                  style={{ padding: '10px 12px', fontSize: 14, cursor: 'pointer', color: isSelected ? '#242424' : '#4b5563',
                    background: isSelected ? '#f5f5f5' : 'transparent', fontWeight: isSelected ? 600 : 400,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  onMouseEnter={e => { if (!isSelected) e.target.style.background = '#f9fafb'; }}
                  onMouseLeave={e => { if (!isSelected) e.target.style.background = 'transparent'; }}>
                  {optLab}
                  {isSelected && <span style={{ color: '#242424', fontSize: 12 }}>✓</span>}
                </div>
              );
            }) : (
              <div style={{ padding: '20px', textAlign: 'center', fontSize: 13, color: '#898989' }}>No results found</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function Card({ children, style }) {
  return <div style={{ ...compStyles.card, ...style }}>{children}</div>;
}

export function InfoStrip({ customer, pkg, device, date, rev, reportNo, items }) {
  const fields = items || [
    ['Customer', customer],
    ['Package', pkg || 'PACKAGE_CODE From BWIP'],
    ['Device', device],
    ['Date', date],
    ['Revision', rev || 'A'],
    ['Report#', reportNo],
  ];

  return (
    <div style={{ background: '#f5f5f5', borderRadius: 8, padding: '12px 16px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px 16px', marginTop: 10 }}>
      {fields.map((field) => {
        const [k, v] = Array.isArray(field) ? field : [field.label, field.value];
        return (
          <div key={k} style={{ fontSize: 12, color: '#898989' }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: '#898989', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>{k}</div>
            <div style={{ color: '#242424', fontWeight: 500 }}>{v || '—'}</div>
          </div>
        );
      })}
    </div>
  );
}

export function ChecklistItem({ label, count, status, onClick }) {
  const isSelected = status === 'ok';
  
  const checkboxStyle = {
    width: 20, height: 20, borderRadius: 5, border: '2px solid',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexShrink: 0, transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
    background: isSelected ? '#242424' : 'transparent',
    borderColor: isSelected ? '#242424' : '#e0e0e0',
  };

  return (
    <div onClick={onClick} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0', borderBottom: '1px solid #f5f5f5', cursor: 'pointer', userSelect: 'none' }}>
      <div style={checkboxStyle}>
        {isSelected && <span style={{ color: '#fff', fontSize: 12, fontWeight: 800 }}>✓</span>}
      </div>
      <span style={{ flex: 1, fontSize: 13, fontWeight: isSelected ? 600 : 500, color: isSelected ? '#242424' : '#898989', transition: 'color 0.2s' }}>{label}</span>
      <span style={{ fontSize: 12, color: '#898989' }}>{count}</span>
    </div>
  );
}

export function CalSans({ size = 16, children, style }) {
  return (
    <span style={{ fontFamily: "'Cal Sans', sans-serif", fontWeight: 600, fontSize: size,
      lineHeight: size >= 24 ? 1.10 : 1.20, letterSpacing: size < 24 ? '0.2px' : 0, color: '#242424', ...style }}>
      {children}
    </span>
  );
}

export { CARD_SHADOW };
