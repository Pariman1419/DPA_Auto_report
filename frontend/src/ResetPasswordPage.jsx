import React, { useState } from 'react';
import { Card, CalSans, Btn, TextInput, FieldLabel } from './Components.jsx';

// Public page — no auth check, no Sidebar. Reached via a real URL
// (/reset-password/{token}) that App.jsx recognizes before the auth gate,
// since the person opening this link is not logged in.
export function ResetPasswordPage({ token }) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!password) {
      setError('Please enter a new password');
      return;
    }
    if (password.length < 6) {
      setError('Minimum 6 characters');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);
    try {
      // Intentionally a plain fetch, not apiFetch — this route is
      // unauthenticated and shouldn't go through apiFetch's 401-redirect
      // logic, which assumes an existing session.
      const res = await fetch(`/api/auth/reset-password/${encodeURIComponent(token)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });

      if (res.ok) {
        setSuccess(true);
      } else {
        // Mirror the backend's own non-enumeration design: don't reveal
        // whether the token was invalid, expired, or already used.
        setError('This reset link is no longer valid. It may have expired or already been used.');
      }
    } catch {
      setError('Connection error. Please check if the server is running.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f7f7f7', padding: 20 }}>
        <div style={{ width: '100%', maxWidth: 400, textAlign: 'center' }}>
          <div style={{ width: 56, height: 56, borderRadius: '50%', background: '#242424', display: 'inline-flex',
            alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 24, marginBottom: 24 }}>✓</div>
          <CalSans size={28} style={{ display: 'block', marginBottom: 8 }}>Password Reset</CalSans>
          <div style={{ fontSize: 14, color: '#666666', marginBottom: 32 }}>
            Your password has been reset. You can now log in with your new password.
          </div>
          <Btn variant="primary" style={{ height: 44, justifyContent: 'center', width: '100%' }}
            onClick={() => { window.location.href = '/'; }}>
            Go to Sign In →
          </Btn>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f7f7f7', padding: 20 }}>
      <div style={{ width: '100%', maxWidth: 400 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ width: 48, height: 48, background: '#242424', borderRadius: 12, display: 'inline-flex',
            alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 24, fontWeight: 700, marginBottom: 16 }}>D</div>
          <CalSans size={32} style={{ display: 'block' }}>Reset Password</CalSans>
          <div style={{ fontSize: 14, color: '#666666', marginTop: 8 }}>Choose a new password for your account</div>
        </div>

        <Card style={{ padding: 32 }}>
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div>
              <FieldLabel>New Password</FieldLabel>
              <TextInput
                placeholder="Min. 6 characters"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div>
              <FieldLabel>Confirm Password</FieldLabel>
              <TextInput
                placeholder="Re-enter new password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>

            {error && <div style={{ fontSize: 13, color: '#ef4444', textAlign: 'center' }}>{error}</div>}

            <Btn variant="primary" style={{ height: 44, justifyContent: 'center' }} disabled={loading}>
              {loading ? 'Resetting…' : 'Reset Password →'}
            </Btn>
          </form>
        </Card>

        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 14, color: '#666666' }}>
          <button
            onClick={() => { window.location.href = '/'; }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#242424', fontWeight: 600,
              fontSize: 14, fontFamily: 'Inter,sans-serif', textDecoration: 'underline', padding: 0 }}>
            Back to Sign In
          </button>
        </div>

        <div style={{ textAlign: 'center', marginTop: 16, fontSize: 12, color: '#737373' }}>
          CIM Development Team.
        </div>
      </div>
    </div>
  );
}
