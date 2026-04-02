/**
 * WattWise Auth — Supabase authentication client
 * Loaded on login page and in base.html for session management.
 */

// Supabase config — loaded from meta tags or inline
const SUPABASE_URL = document.querySelector('meta[name="supabase-url"]')?.content || '';
const SUPABASE_ANON_KEY = document.querySelector('meta[name="supabase-anon-key"]')?.content || '';

// Simple Supabase REST auth (no SDK dependency — keeps bundle small)
const supabaseAuth = {
  async signInWithPassword(email, password) {
    const r = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'apikey': SUPABASE_ANON_KEY,
      },
      body: JSON.stringify({ email, password }),
    });
    return r.json();
  },

  async signUp(email, password) {
    const r = await fetch(`${SUPABASE_URL}/auth/v1/signup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'apikey': SUPABASE_ANON_KEY,
      },
      body: JSON.stringify({ email, password }),
    });
    return r.json();
  },

  async signInWithOtp(email) {
    const r = await fetch(`${SUPABASE_URL}/auth/v1/otp`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'apikey': SUPABASE_ANON_KEY,
      },
      body: JSON.stringify({ email }),
    });
    return r.json();
  },

  async refreshSession() {
    const refreshToken = localStorage.getItem('sb-refresh-token');
    if (!refreshToken) return null;
    try {
      const r = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'apikey': SUPABASE_ANON_KEY,
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!r.ok) {
        this.clearSession();
        return null;
      }
      const data = await r.json();
      if (data.access_token) {
        this.setSession(data);
        return data;
      }
      this.clearSession();
      return null;
    } catch {
      return null;
    }
  },

  async getUser() {
    const token = this.getToken();
    if (!token) return null;
    try {
      const r = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
        headers: {
          'apikey': SUPABASE_ANON_KEY,
          'Authorization': `Bearer ${token}`,
        },
      });
      if (!r.ok) return null;
      return r.json();
    } catch {
      return null;
    }
  },

  setSession(data) {
    if (data.access_token) {
      localStorage.setItem('sb-access-token', data.access_token);
      localStorage.setItem('sb-refresh-token', data.refresh_token || '');
      localStorage.setItem('sb-expires-at', String(Date.now() + (data.expires_in || 3600) * 1000));
      // Set as cookie for server-side auth
      document.cookie = `sb-access-token=${data.access_token};path=/;max-age=${data.expires_in || 3600};SameSite=Strict`;
    }
  },

  getToken() {
    return localStorage.getItem('sb-access-token');
  },

  clearSession() {
    localStorage.removeItem('sb-access-token');
    localStorage.removeItem('sb-refresh-token');
    localStorage.removeItem('sb-expires-at');
    document.cookie = 'sb-access-token=;path=/;max-age=0';
  },

  isAuthenticated() {
    return !!this.getToken();
  },

  isTokenExpiringSoon() {
    const expiresAt = parseInt(localStorage.getItem('sb-expires-at') || '0', 10);
    return expiresAt > 0 && (expiresAt - Date.now()) < 5 * 60 * 1000; // 5 min buffer
  },
};

// Auto-refresh token before expiry
(async function autoRefresh() {
  if (!supabaseAuth.isAuthenticated()) return;
  if (supabaseAuth.isTokenExpiringSoon()) {
    await supabaseAuth.refreshSession();
  }
  setTimeout(autoRefresh, 60 * 1000); // check every minute
})();

// Handle auth callback (magic link / OAuth redirect)
// Supabase redirects with #access_token=...&refresh_token=...&...
(function handleAuthCallback() {
  const hash = window.location.hash;
  if (!hash || !hash.includes('access_token=')) return;
  const params = new URLSearchParams(hash.substring(1));
  const accessToken = params.get('access_token');
  const refreshToken = params.get('refresh_token');
  const expiresIn = parseInt(params.get('expires_in') || '3600', 10);
  if (accessToken) {
    supabaseAuth.setSession({ access_token: accessToken, refresh_token: refreshToken, expires_in: expiresIn });
    // Clean the URL and redirect to dashboard
    window.history.replaceState(null, '', window.location.pathname);
    if (window.location.pathname === '/login' || window.location.pathname === '/auth/callback') {
      window.location.href = '/dashboard';
    }
  }
})();

// ---- Login page functions ----

function showMessage(text, type = 'info') {
  const el = document.getElementById('login-message');
  if (!el) return;
  el.style.display = 'block';
  el.style.background = type === 'error' ? 'var(--danger, #e53e3e)' : type === 'success' ? 'var(--success, #38a169)' : 'var(--accent-light, #ebf8ff)';
  el.style.color = type === 'error' ? '#fff' : type === 'success' ? '#fff' : 'var(--accent, #3182ce)';
  el.textContent = text;
}

async function signInEmail() {
  const email = document.getElementById('login-email')?.value.trim();
  const password = document.getElementById('login-password')?.value;
  if (!email || !password) { showMessage('Email and password required.', 'error'); return; }

  showMessage('Signing in...');
  try {
    const data = await supabaseAuth.signInWithPassword(email, password);
    console.log('Sign in response:', JSON.stringify(data).substring(0, 200));
    if (data.access_token) {
      supabaseAuth.setSession(data);
      window.location.href = '/dashboard';
    } else {
      showMessage(data.error_description || data.msg || data.error || 'Sign in failed.', 'error');
    }
  } catch (e) {
    console.error('Sign in error:', e);
    showMessage('Connection error: ' + e.message, 'error');
  }
}

async function signUpEmail() {
  const email = document.getElementById('login-email')?.value.trim();
  const password = document.getElementById('login-password')?.value;
  if (!email || !password) { showMessage('Email and password required.', 'error'); return; }
  if (password.length < 6) { showMessage('Password must be at least 6 characters.', 'error'); return; }

  showMessage('Creating account...');
  const data = await supabaseAuth.signUp(email, password);
  if (data.access_token) {
    supabaseAuth.setSession(data);
    window.location.href = '/dashboard';
  } else if (data.id) {
    showMessage('Account created! Check your email to confirm, then sign in.', 'success');
  } else {
    showMessage(data.error_description || data.msg || 'Sign up failed.', 'error');
  }
}

async function resetPassword() {
  const email = document.getElementById('login-email')?.value.trim();
  if (!email) { showMessage('Enter your email first.', 'error'); return; }

  showMessage('Sending reset link...');
  try {
    const r = await fetch(`${SUPABASE_URL}/auth/v1/recover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'apikey': SUPABASE_ANON_KEY },
      body: JSON.stringify({ email }),
    });
    if (r.ok) {
      showMessage('Password reset link sent! Check your email.', 'success');
    } else {
      const data = await r.json();
      showMessage(data.error_description || data.msg || 'Failed to send reset link.', 'error');
    }
  } catch (e) {
    showMessage('Connection error: ' + e.message, 'error');
  }
}

async function signInMagicLink() {
  const email = document.getElementById('login-email')?.value.trim();
  if (!email) { showMessage('Enter your email first.', 'error'); return; }

  showMessage('Sending magic link...');
  const data = await supabaseAuth.signInWithOtp(email);
  if (data.error) {
    showMessage(data.error_description || 'Failed to send magic link.', 'error');
  } else {
    showMessage('Magic link sent! Check your email.', 'success');
  }
}

// ---- Auth header injection for all API calls ----
// Override fetch to automatically add auth token to /api/ calls
const _originalFetch = window.fetch;
window.fetch = function(url, opts = {}) {
  if (typeof url === 'string' && url.startsWith('/api/')) {
    const token = supabaseAuth.getToken();
    if (token) {
      opts.headers = opts.headers || {};
      if (opts.headers instanceof Headers) {
        opts.headers.set('Authorization', `Bearer ${token}`);
      } else {
        opts.headers['Authorization'] = `Bearer ${token}`;
      }
    }
  }
  return _originalFetch.call(this, url, opts);
};
