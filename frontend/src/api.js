// Auth helpers — token lives in an httpOnly cookie set by the server.
// JS only manages the user-profile object (non-sensitive display data).

export function getUser() {
  const raw = localStorage.getItem('dpa_user');
  return raw ? JSON.parse(raw) : null;
}

export function setUser(userData) {
  localStorage.setItem('dpa_user', JSON.stringify(userData));
}

export function clearAuth() {
  localStorage.removeItem('dpa_user');
}

export async function logout() {
  clearAuth();
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
  } catch {
    // best-effort
  }
}

// Guard against multiple concurrent 401 responses causing a redirect storm.
let _redirecting = false;

export async function apiFetch(url, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  // credentials: 'include' ensures the httpOnly cookie is sent with every request.
  const res = await fetch(url, { ...options, headers, credentials: 'include' });

  if (res.status === 401 && !_redirecting) {
    _redirecting = true;
    clearAuth();
    window.location.href = '/';
  }
  return res;
}
