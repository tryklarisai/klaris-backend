import React, { useEffect, useState } from 'react';
import {
  Box, Button, Card, CardContent, Typography, CircularProgress, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, MenuItem, Alert
} from '@mui/material';
import { useNavigate } from 'react-router-dom';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const connectorTypes = [
  { value: 'postgres', label: 'Postgres' },
  { value: 'google_drive', label: 'Google Drive' }
];

type Connector = {
  connector_id: string;
  type: string;
  status: string;
  last_schema_fetch?: string;
  error_message?: string;
};

export default function ConnectorsPage() {
  const navigate = useNavigate();
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [addOpen, setAddOpen] = useState(false);
  const [addLoading, setAddLoading] = useState(false);
  const [addErr, setAddErr] = useState<string | null>(null);
  const [form, setForm] = useState({
    type: 'postgres',
    mcp_url: '',
    username: '',
    password: '',
    client_id: '',
    client_secret: ''
  });

  useEffect(() => {
    const tStr = window.localStorage.getItem('klaris_tenant');
    if (!tStr) {
      navigate('/login', { replace: true });
      return;
    }
    const t = JSON.parse(tStr);
    setTenantId(t.tenant_id);
  }, [navigate]);

  useEffect(() => {
    if (tenantId) fetchConnectors();
    // eslint-disable-next-line
  }, [tenantId]);

  const fetchConnectors = async () => {
    if (!tenantId) return;
    setLoading(true);
    setError(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!resp.ok) throw new Error('Failed to fetch connectors');
      const data = await resp.json();
      setConnectors(data.connectors || []);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch connectors');
    } finally {
      setLoading(false);
    }
  };

  const handleAddConnector = async () => {
    setAddErr(null);
    if (!form.mcp_url || !form.type) {
      setAddErr('Connector type and MCP URL are required.');
      return;
    }
    setAddLoading(true);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          type: form.type,
          config: {
            mcp_url: form.mcp_url,
            username: form.username,
            password: form.password,
            client_id: form.client_id,
            client_secret: form.client_secret,
          }
        })
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || 'Failed to add connector');
      setAddOpen(false);
      setForm({ type: 'postgres', mcp_url: '', username: '', password: '', client_id: '', client_secret: '' });
      fetchConnectors();
    } catch (err: any) {
      setAddErr(err.message || 'Failed to add connector');
    } finally {
      setAddLoading(false);
    }
  };

  return (
    <Box sx={{ mt: 7, maxWidth: 800, mx: 'auto' }}>
      <Typography variant="h4" mb={2}>Connectors</Typography>
      <Typography variant="h6" sx={{ mb: 1 }}>Add a Connector</Typography>
      <Box sx={{ display: 'flex', gap: 3, mb: 3 }}>
        <Card
          sx={{ width: 180, cursor: 'pointer', textAlign: 'center', p: 2 }}
          onClick={() => setAddOpen(true)}
        >
          {/* Postgres Icon (simple SVG) */}
          <Box sx={{ width: 60, height: 60, mx: 'auto', my: 1 }}>
            <svg viewBox="0 0 60 60" width="60" height="60">
              <circle cx="30" cy="30" r="28" stroke="#1976d2" strokeWidth="3" fill="#fff" />
              <ellipse cx="30" cy="35" rx="14" ry="9" fill="#90caf9" stroke="#1976d2" strokeWidth="2" />
              <ellipse cx="30" cy="28" rx="12" ry="5" fill="#1976d2" opacity="0.4" />
            </svg>
          </Box>
          <Typography>Postgres</Typography>
        </Card>
        <Card
          sx={{ width: 180, cursor: 'pointer', textAlign: 'center', p: 2 }}
          onClick={() => {
            // Launch Google Drive OAuth flow in new tab
            if (!tenantId) return;
            const url = `${API_URL}/connectors/google-drive/authorize?tenant_id=${tenantId}`;
            window.open(url, '_blank', 'noopener,noreferrer');
          }}
        >
          {/* Google Drive SVG Icon */}
          <Box sx={{ width: 60, height: 60, mx: 'auto', my: 1 }}>
            <svg width="60" height="60" viewBox="0 0 60 60">
              <polygon fill="#0F9D58" points="30,6 54,46 46,46 22,6" />
              <polygon fill="#F4B400" points="6,46 30,6 22,6 6,46" />
              <polygon fill="#1976D2" points="6,46 46,46 54,46 14,46" />
              <polygon fill="#FF7043" points="30,54 46,46 14,46" opacity="0.7" />
            </svg>
          </Box>
          <Typography>Google Drive</Typography>
        </Card>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {loading ? <CircularProgress sx={{ mt: 2 }} /> : (
        connectors.length === 0 ? <Typography>No connectors found.</Typography> : (
          connectors.map(conn => (
            <Card key={conn.connector_id} sx={{ mb: 2, cursor: 'pointer' }} onClick={() => navigate(`/connectors/${conn.connector_id}`)}>
              <CardContent>
                <Typography variant="h6" sx={{ mb: 0.5 }}>{conn.type} — <b>{conn.status}</b></Typography>
                <Typography variant="body2" color="text.secondary">ID: {conn.connector_id}</Typography>
                <Typography variant="body2" color="text.secondary">
                  Last schema fetch: {conn.last_schema_fetch ? new Date(conn.last_schema_fetch).toLocaleString() : 'Never'}
                </Typography>
                {conn.error_message && <Alert severity="warning" sx={{ mt: 1 }}>Last error: {conn.error_message}</Alert>}
              </CardContent>
            </Card>
          ))
        )
      )}

      {/* Add Connector Modal (for Postgres) */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add a Connector</DialogTitle>
        <DialogContent>
          <Box my={2} display="flex" gap={2} flexDirection="column">
            <TextField
              select
              label="Connector Type"
              value={form.type}
              onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
              fullWidth
            >
              {connectorTypes
                .filter(opt => opt.value === 'postgres')
                .map(opt => (
                  <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                ))}
            </TextField>
            <TextField
              label="MCP Endpoint URL"
              value={form.mcp_url}
              onChange={e => setForm(f => ({ ...f, mcp_url: e.target.value }))}
              fullWidth
              required
            />
            <TextField
              label="Username"
              value={form.username}
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Password"
              type="password"
              value={form.password}
              onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Client ID (optional)"
              value={form.client_id}
              onChange={e => setForm(f => ({ ...f, client_id: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Client Secret (optional)"
              type="password"
              value={form.client_secret}
              onChange={e => setForm(f => ({ ...f, client_secret: e.target.value }))}
              fullWidth
            />
          </Box>
          {addErr && <Alert severity="error" sx={{ mt: 2 }}>{addErr}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)} disabled={addLoading}>Cancel</Button>
          <Button onClick={handleAddConnector} disabled={addLoading || !form.type || !form.mcp_url}>
            {addLoading ? <CircularProgress size={22} /> : 'Add'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
