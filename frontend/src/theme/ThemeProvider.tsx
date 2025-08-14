import React from 'react';
import { ThemeProvider as MuiThemeProvider, CssBaseline } from '@mui/material';
import { buildTheme, ColorMode } from './index';
import { config } from '../config';

type Props = { children: React.ReactNode };

export default function ThemeProvider({ children }: Props) {
  const [mode, setMode] = React.useState<ColorMode>(() => (localStorage.getItem('ui_mode') as ColorMode) || 'light');

  const theme = React.useMemo(() => buildTheme(mode, config.primaryColor), [mode]);

  const toggleMode = React.useCallback(() => {
    const next = mode === 'light' ? 'dark' : 'light';
    localStorage.setItem('ui_mode', next);
    setMode(next);
  }, [mode]);

  return (
    <MuiThemeProvider theme={theme}>
      <CssBaseline />
      <ModeContext.Provider value={{ mode, toggleMode }}>
        {children}
      </ModeContext.Provider>
    </MuiThemeProvider>
  );
}

export const ModeContext = React.createContext<{ mode: ColorMode; toggleMode: () => void }>({
  mode: 'light',
  toggleMode: () => {},
});


