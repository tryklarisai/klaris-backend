import { createTheme, ThemeOptions } from '@mui/material/styles';
import { deepmerge } from '@mui/utils';

export type ColorMode = 'light' | 'dark';

export function buildTheme(mode: ColorMode, primaryColor: string) {
  const base: ThemeOptions = {
    palette: {
      mode,
      primary: { main: primaryColor },
      background: {
        default: mode === 'light' ? '#f7f9fc' : '#0b1020',
        paper: mode === 'light' ? '#ffffff' : '#121a2e',
      },
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, 'Apple Color Emoji', 'Segoe UI Emoji'",
      h1: { fontWeight: 700 },
      h2: { fontWeight: 700 },
      h3: { fontWeight: 700 },
      h4: { fontWeight: 700 },
      h5: { fontWeight: 600 },
      h6: { fontWeight: 600 },
      button: { textTransform: 'none', fontWeight: 600 },
    },
    components: {
      MuiButton: {
        defaultProps: { size: 'medium' },
      },
      MuiCard: {
        styleOverrides: {
          root: { boxShadow: mode === 'light' ? '0 2px 16px rgba(16,24,40,0.06)' : '0 2px 16px rgba(0,0,0,0.5)' },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: { boxShadow: 'none', borderBottom: mode === 'light' ? '1px solid #e6e8eb' : '1px solid rgba(255,255,255,0.1)' },
        },
      },
    },
  };

  return createTheme(deepmerge(base, {}));
}


