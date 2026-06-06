import React, { useState } from 'react';
import { Card, CalSans, Btn, TextInput, FieldLabel } from './Components.jsx';
import { setUser } from './api.js';

export function LoginPage({ onLoginSuccess, onShowRegister }) {
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!userId || !password) {
      setError('Please enter both Employee ID and password');
      return;
    }

    setLoading(true);
    setError('');

    try {
      // credentials: 'include' is required so the browser stores the httpOnly cookie
      // returned by Set-Cookie in the response.
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ userId, password }),
      });

      const data = await res.json();

      if (res.ok) {
        // Store only the user profile (not the token — it lives in the httpOnly cookie).
        setUser(data.user);
        onLoginSuccess(data.user);
      } else {
        setError(data.detail || 'Login failed');
      }
    } catch {
      setError('Connection error. Please check if the server is running.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f7f7f7', padding: 20 }}>
      <div style={{ width: '100%', maxWidth: 400 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ width: 48, height: 48, background: '#242424', borderRadius: 12, display: 'inline-flex',
            alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 24, fontWeight: 700, marginBottom: 16 }}>D</div>
          <CalSans size={32} style={{ display: 'block' }}>DPA QA Manager</CalSans>
          <div style={{ fontSize: 14, color: '#666666', marginTop: 8 }}>Automated Reporting Pipeline</div>
        </div>

        <Card style={{ padding: 32 }}>
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div>
              <FieldLabel>Employee ID</FieldLabel>
              <TextInput
                placeholder="e.g. 10455"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
              />
            </div>
            <div>
              <FieldLabel>Password</FieldLabel>
              <TextInput
                placeholder="••••••••"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && <div style={{ fontSize: 13, color: '#ef4444', textAlign: 'center' }}>{error}</div>}

            <Btn variant="primary" style={{ height: 44, justifyContent: 'center' }} disabled={loading}>
              {loading ? 'Authenticating…' : 'Sign In →'}
            </Btn>
          </form>
        </Card>

        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 14, color: '#666666' }}>
          Don't have an account?{' '}
          <button
            onClick={onShowRegister}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#242424', fontWeight: 600,
              fontSize: 14, fontFamily: 'Inter,sans-serif', textDecoration: 'underline', padding: 0 }}>
            Create account
          </button>
        </div>

        <div style={{ textAlign: 'center', marginTop: 16, fontSize: 12, color: '#737373' }}>
          CIM Development Team.
        </div>
      </div>
    </div>
  );
}
