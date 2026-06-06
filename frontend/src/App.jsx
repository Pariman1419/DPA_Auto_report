import React, { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar.jsx';
import { CreateReport } from './CreateReport.jsx';
import { HistoryPage } from './HistoryPage.jsx';
import { CalSans, Btn } from './Components.jsx';
import { LoginPage } from './LoginPage.jsx';
import { RegisterPage } from './RegisterPage.jsx';
import { getUser, setUser, logout, apiFetch } from './api.js';

export default function App() {
  const [page, setPage] = useState('create');
  const [authMode, setAuthMode] = useState('login'); // 'login' | 'register'
  const [stats, setStats] = useState({ total: 0, generated: 0, failed: 0 });
  const [user, setUserState] = useState(() => getUser());

  useEffect(() => {
    if (page === 'dashboard' && user) {
      apiFetch('/api/stats')
        .then(r => r.json())
        .then(data => setStats(data))
        .catch(err => console.error('Failed to fetch stats:', err));
    }
  }, [page, user]);

  const handleLoginSuccess = (userData) => {
    setUser(userData);
    setUserState(userData);
    setAuthMode('login');
  };

  const handleLogout = async () => {
    await logout();
    setUserState(null);
    setPage('create');
  };

  if (!user) {
    if (authMode === 'register') {
      return (
        <RegisterPage
          onShowLogin={() => setAuthMode('login')}
          onRegisterSuccess={() => setAuthMode('login')}
        />
      );
    }
    return (
      <LoginPage
        onLoginSuccess={handleLoginSuccess}
        onShowRegister={() => setAuthMode('register')}
      />
    );
  }

  const contentPad = 48;

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#f7f7f7' }}>
      <Sidebar page={page} onNav={setPage} user={user} onLogout={handleLogout} />

      <main style={{ flex: 1, padding: `${contentPad}px`, overflowY: 'auto' }}>
        <div style={{ maxWidth: 1000, margin: '0 auto' }}>
          {page === 'create' && <CreateReport user={user} />}
          {page === 'history' && <HistoryPage />}
          {page === 'dashboard' && (
            <div>
              <CalSans size={32} style={{ display: 'block', marginBottom: 12 }}>Dashboard</CalSans>
              <div style={{ fontSize: 14, color: '#898989', marginBottom: 40 }}>Overview of your DPA report activity.</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 32 }}>
                {[
                  ['Total Reports', stats.total],
                  ['Generated', stats.generated],
                  ['Failed', stats.failed],
                ].map(([label, val]) => (
                  <div key={label} style={{ background: '#fff', borderRadius: 12, padding: '20px 24px',
                    boxShadow: 'rgba(19,19,22,0.7) 0px 1px 5px -4px, rgba(34,42,53,0.08) 0px 0px 0px 1px, rgba(34,42,53,0.05) 0px 4px 8px 0px' }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#898989', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>{label}</div>
                    <div style={{ fontFamily: "'Cal Sans',sans-serif", fontSize: 36, fontWeight: 600, color: '#242424', lineHeight: 1.1 }}>{val}</div>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <Btn variant="primary" onClick={() => setPage('create')}>+ Create New Report</Btn>
                <Btn variant="ghost" onClick={() => setPage('history')}>View History</Btn>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
