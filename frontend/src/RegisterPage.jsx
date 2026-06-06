import React, { useState } from 'react';
import { Card, CalSans, Btn, TextInput, FieldLabel } from './Components.jsx';

export function RegisterPage({ onShowLogin }) {
  const [form, setForm] = useState({ userId: '', fullName: '', email: '', password: '', confirmPassword: '' });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const set = (k) => (e) => setForm(prev => ({ ...prev, [k]: e.target.value }));

  const validate = () => {
    const errs = {};
    if (!form.userId.trim()) errs.userId = 'Employee ID is required';
    else if (!/^\d{4,6}$/.test(form.userId.trim())) errs.userId = 'Must be 4–6 digits (e.g. 10455)';
    if (!form.fullName.trim()) errs.fullName = 'Full name is required';
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = 'Invalid email format';
    if (!form.password) errs.password = 'Password is required';
    else if (form.password.length < 6) errs.password = 'Minimum 6 characters';
    if (form.password !== form.confirmPassword) errs.confirmPassword = 'Passwords do not match';
    return errs;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length) return;

    setLoading(true);
    setApiError('');

    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId: form.userId.trim(),
          fullName: form.fullName.trim(),
          email: form.email.trim() || null,
          password: form.password,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        setSuccess(true);
      } else {
        setApiError(data.detail || 'Registration failed');
      }
    } catch {
      setApiError('Connection error. Please check if the server is running.');
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
          <CalSans size={28} style={{ display: 'block', marginBottom: 8 }}>Account Created</CalSans>
          <div style={{ fontSize: 14, color: '#666666', marginBottom: 32 }}>
            Your account has been created. Sign in to get started.
          </div>
          <Btn variant="primary" style={{ height: 44, justifyContent: 'center', width: '100%' }} onClick={onShowLogin}>
            Go to Sign In →
          </Btn>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f7f7f7', padding: 20 }}>
      <div style={{ width: '100%', maxWidth: 400 }}>
        <button 
          onClick={onShowLogin}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#666666', fontSize: 14, 
            display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16, padding: 0 }}>
          ← Back to Login
        </button>

        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ width: 48, height: 48, background: '#242424', borderRadius: 12, display: 'inline-flex',
            alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 24, fontWeight: 700, marginBottom: 16 }}>D</div>
          <CalSans size={32} style={{ display: 'block' }}>Create Account</CalSans>
          <div style={{ fontSize: 14, color: '#666666', marginTop: 8 }}>DPA QA Manager — NXP Semiconductors</div>
        </div>

        <Card style={{ padding: 32 }}>
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <FieldLabel>Employee ID</FieldLabel>
                <TextInput placeholder="e.g. 10455" value={form.userId} onChange={set('userId')} error={errors.userId} />
              </div>
              <div>
                <FieldLabel>Full Name</FieldLabel>
                <TextInput placeholder="Your name" value={form.fullName} onChange={set('fullName')} error={errors.fullName} />
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                <FieldLabel>Email</FieldLabel>
                <span style={{ fontSize: 11, color: '#666666', fontFamily: 'Inter,sans-serif', fontWeight: 400,
                  background: '#f5f5f5', padding: '1px 7px', borderRadius: 9999, lineHeight: 1.6 }}>optional</span>
              </div>
              <TextInput
                placeholder="e.g. name@nxp.com"
                type="email"
                value={form.email}
                onChange={set('email')}
                error={errors.email}
              />
            </div>

            <div>
              <FieldLabel>Password</FieldLabel>
              <TextInput placeholder="Min. 6 characters" type="password" value={form.password} onChange={set('password')} error={errors.password} />
            </div>

            <div>
              <FieldLabel>Confirm Password</FieldLabel>
              <TextInput placeholder="Re-enter password" type="password" value={form.confirmPassword} onChange={set('confirmPassword')} error={errors.confirmPassword} />
            </div>

            {apiError && <div style={{ fontSize: 13, color: '#ef4444', textAlign: 'center' }}>{apiError}</div>}

            <Btn variant="primary" style={{ height: 44, justifyContent: 'center', marginTop: 4 }} disabled={loading}>
              {loading ? 'Creating account…' : 'Create Account →'}
            </Btn>
          </form>
        </Card>

        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 14, color: '#666666' }}>
          Already have an account?{' '}
          <button
            onClick={onShowLogin}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#242424', fontWeight: 600,
              fontSize: 14, fontFamily: 'Inter,sans-serif', textDecoration: 'underline', padding: 0 }}>
            Sign in
          </button>
        </div>

        <div style={{ textAlign: 'center', marginTop: 16, fontSize: 12, color: '#737373' }}>
            CIM Development Team.
        </div>
      </div>
    </div>
  );
}
