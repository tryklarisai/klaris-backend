import React from 'react';
import { Snackbar, Alert, AlertColor } from '@mui/material';

type SnackbarMessage = { message: string; severity?: AlertColor } | null;

export const SnackbarContext = React.createContext<{
  notify: (message: string, severity?: AlertColor) => void;
}>({ notify: () => {} });

export default function SnackbarProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [msg, setMsg] = React.useState<SnackbarMessage>(null);

  const notify = React.useCallback((message: string, severity: AlertColor = 'info') => {
    setMsg({ message, severity });
    setOpen(true);
  }, []);

  return (
    <SnackbarContext.Provider value={{ notify }}>
      {children}
      <Snackbar
        open={open}
        autoHideDuration={3500}
        onClose={() => setOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={() => setOpen(false)} severity={msg?.severity || 'info'} elevation={3} variant="filled">
          {msg?.message}
        </Alert>
      </Snackbar>
    </SnackbarContext.Provider>
  );
}


