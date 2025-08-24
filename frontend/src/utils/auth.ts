export function getToken(): string | null {
  try {
    return window.localStorage.getItem('klaris_jwt');
  } catch {
    return null;
  }
}

export function parseJwt(token: string): any | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const json = decodeURIComponent(atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string): boolean {
  const payload = parseJwt(token);
  if (!payload || typeof payload !== 'object') return true;
  const expSec = Number(payload.exp || 0);
  if (!expSec) return true;
  const nowSec = Math.floor(Date.now() / 1000);
  return nowSec >= expSec;
}

export function clearAuthStorage() {
  try {
    window.localStorage.removeItem('klaris_jwt');
    window.localStorage.removeItem('klaris_user');
    window.localStorage.removeItem('klaris_tenant');
  } catch {
    // ignore
  }
}


