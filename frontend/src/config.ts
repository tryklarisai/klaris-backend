// Centralized runtime configuration. Reads from window.__APP_CONFIG__ (if present)
// and REACT_APP_* environment variables. Avoids hardcoded values in components.

export interface AppConfig {
  apiBaseUrl: string;
  brandName: string;
  primaryColor: string;
  logoUrl?: string;
  googleApiKey?: string;
}

declare global {
  interface Window {
    __APP_CONFIG__?: Partial<AppConfig>;
  }
}

function readEnv(name: string): string | undefined {
  // CRA exposes REACT_APP_* at build time
  // eslint-disable-next-line no-restricted-globals
  return (process.env as any)?.[name] as string | undefined;
}

export const config: AppConfig = {
  apiBaseUrl:
    (typeof window !== 'undefined' && window.__APP_CONFIG__?.apiBaseUrl) ||
    readEnv('REACT_APP_API_URL') ||
    'http://localhost:8000',
  brandName:
    (typeof window !== 'undefined' && window.__APP_CONFIG__?.brandName) ||
    readEnv('REACT_APP_BRAND_NAME') ||
    'Klaris',
  primaryColor:
    (typeof window !== 'undefined' && window.__APP_CONFIG__?.primaryColor) ||
    readEnv('REACT_APP_PRIMARY_COLOR') ||
    '#1976d2',
  logoUrl:
    (typeof window !== 'undefined' && window.__APP_CONFIG__?.logoUrl) ||
    readEnv('REACT_APP_LOGO_URL') ||
    undefined,
  googleApiKey:
    (typeof window !== 'undefined' && window.__APP_CONFIG__?.googleApiKey) ||
    readEnv('REACT_APP_GOOGLE_API_KEY') ||
    undefined,
};

export function buildApiUrl(path: string): string {
  const base = (config.apiBaseUrl || '').replace(/\/+$/, '');
  if (!path) return base;
  const suffix = path.startsWith('/') ? path : `/${path}`;
  // Collapse accidental double slashes but keep protocol intact
  return `${base}${suffix}`.replace(/([^:]\/)\/+/, '$1');
}


