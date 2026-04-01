/**
 * HeatSmart Auth — Supabase authentication client
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

  setSession(data) {
    if (data.access_token) {
      localStorage.setItem('sb-access-token', data.access_token);
      localStorage.setItem('sb-refresh-token', data.refresh_token || '');
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
    document.cookie = 'sb-access-token=;path=/;max-age=0';
  },

  isAuthenticated() {
    return !!this.getToken();
  },
};

// ---- Login page functions ----

function showMessage(text, type = 'info') {
  const el = document.getElementById('login-message');
  if (!el) return;
  el.style.display = 'block';
  el.style.background = type === 'error' ? '#fed7d7' : type === 'success' ? '#c6f6d5' : 'var(--accent-light)';
  el.style.color = type === 'error' ? '#822727' : type === 'success' ? '#22543d' : 'var(--accent)';
  el.textContent = text;
}

async function signInEmail() {
  const email = document.getElementById('login-email')?.value.trim();
  const password = document.getElementById('login-password')?.value;
  if (!email || !password) { showMessage('Email and password required.', 'error'); return; }

  showMessage('Signing in...');
  const data = await supabaseAuth.signInWithPassword(email, password);
  if (data.access_token) {
    supabaseAuth.setSession(data);
    window.location.href = '/dashboard';
  } else {
    showMessage(data.error_description || data.msg || 'Sign in failed.', 'error');
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
