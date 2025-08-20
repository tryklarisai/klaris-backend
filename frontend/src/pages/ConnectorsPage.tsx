import React, { useEffect, useState } from 'react';
import {
  Box, Button, Typography, Alert, TextField, MenuItem, Stack, Chip, Dialog, DialogTitle, DialogContent, DialogActions, Link
} from '@mui/material';
// Avoid Grid to reduce typings complexity in modal; simple Box layout instead
import { LoadingButton } from '@mui/lab';
import { DataGrid, GridColDef, GridRowParams } from '@mui/x-data-grid';
import { useNavigate } from 'react-router-dom';
import { buildApiUrl } from '../config';
import { ReactComponent as GoogleDriveSvg } from '../assets/connectors/google-drive.svg';
import { ReactComponent as PostgresSvg } from '../assets/connectors/postgres.svg';
import Tooltip from '@mui/material/Tooltip';
import { formatRelativeTime, formatLocalDatetime } from '../utils/date';

const API_URL = buildApiUrl('');

const connectorTypes = [
  { value: 'postgres', label: 'Postgres' },
  { value: 'google_drive', label: 'Google Drive' }
];

type Connector = {
  connector_id: string;
  name?: string;
  type: string;
  status: string;
  created_at?: string;
  last_schema_fetch?: string;
  error_message?: string;
};

export default function ConnectorsPage() {
  const navigate = useNavigate();
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPostgresForm, setShowPostgresForm] = useState(false);
  // Removed tabs - now showing new connector by default with Your Connectors below

  // Modal state
  const [addLoading, setAddLoading] = useState(false);
  const [addErr, setAddErr] = useState<string | null>(null);
  const [form, setForm] = useState({
    type: 'postgres',
    name: '',
    host: '',
    port: '',
    user: '',
    password: '',
    database: '',
    mfa_type: '',
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
    if (!form.type || !form.host || !form.user || !form.password || !form.database) {
      setAddErr('All fields are required.');
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
          name: form.name || undefined,
          config: {
            host: form.host,
            port: form.port,
            user: form.user,
            password: form.password,
            database: form.database,
            mfa_type: form.mfa_type || undefined,
          }
        })
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || 'Failed to add connector');
      setShowPostgresForm(false);
      setForm({ type: 'postgres', name: '', host: '', port: '', user: '', password: '', database: '', mfa_type: '' });
      fetchConnectors();
    } catch (err: any) {
      setAddErr(err.message || 'Failed to add connector');
    } finally {
      setAddLoading(false);
    }
  };

  const columns: GridColDef[] = [
    { field: 'name', headerName: 'Name', flex: 1, minWidth: 160, renderCell: ({ value, row }) => value || `${row.type} Connector` },
    { field: 'type', headerName: 'Type', width: 120 },
    { field: 'status', headerName: 'Status', width: 100, renderCell: ({ value }) => (<Chip label={value} color={value === 'active' ? 'success' : 'default'} size="small" />) },
    {
      field: 'created_at',
      headerName: 'Created',
      width: 150,
      renderCell: (params) => params.value ? (
        <Tooltip title={formatLocalDatetime(params.value)}>
          <Chip size="small" variant="outlined" label={formatRelativeTime(params.value)} />
        </Tooltip>
      ) : <Chip size="small" variant="outlined" label="—" />,
    },
    {
      field: 'last_schema_fetch',
      headerName: 'Last Schema Fetch',
      width: 160,
      renderCell: (params) => params.value ? (
        <Tooltip title={formatLocalDatetime(params.value)}>
          <Chip size="small" variant="outlined" label={formatRelativeTime(params.value)} />
        </Tooltip>
      ) : <Chip size="small" variant="outlined" label="Never" />,
    },
  ];

  return (
    <Box sx={{ mt: 7 }}>
      <Typography variant="h4" sx={{ mb: 3 }}>Connectors</Typography>
      
      {/* New Connector Section */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h6" mb={2}>Add New Connector</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)' }, gap: 2, minWidth: 0 }}>
          {/* Google Drive */}
          <Box sx={{ p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 2, cursor: 'pointer', minWidth: 0 }}
            onClick={() => {
              if (!tenantId) return;
              const url = `${API_URL}/connectors/google-drive/authorize?tenant_id=${tenantId}`;
              window.location.href = url; // Use same window for smoother flow
            }}
          >
            <Stack direction="row" spacing={2} alignItems="center" sx={{ minWidth: 0 }}>
              <GoogleDriveSvg width={32} height={32} style={{ flexShrink: 0 }} />
              <Box sx={{ minWidth: 0 }}>
                <Typography fontWeight={600}>Google Drive</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  Connect to Google Drive documents and spreadsheets
                </Typography>
                <Stack direction="row" spacing={1} mt={1}>
                  <Chip size="small" label="Integration" />
                </Stack>
              </Box>
            </Stack>
          </Box>

          {/* Postgres */}
          <Box sx={{ p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 2, cursor: 'pointer', minWidth: 0 }} onClick={() => setShowPostgresForm(true)}>
            <Stack direction="row" spacing={2} alignItems="center" sx={{ minWidth: 0 }}>
              <PostgresSvg width={32} height={32} style={{ flexShrink: 0 }} />
              <Box sx={{ minWidth: 0 }}>
                <Typography fontWeight={600}>Postgres</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  Connect to your Postgres database
                </Typography>
                <Stack direction="row" spacing={1} mt={1}>
                  <Chip size="small" label="MCP" />
                </Stack>
              </Box>
            </Stack>
          </Box>

          {/* Disabled placeholders */}
          {['Microsoft OneDrive', 'SharePoint', 'Google Ads', 'Stripe', 'Intercom', 'Notion', 'GitHub', 'RevenueCat'].map((name) => (
            <Box key={name} sx={{ p: 2, border: '1px dashed', borderColor: 'divider', borderRadius: 2, opacity: 0.5, cursor: 'not-allowed', minWidth: 0 }}>
              <Stack direction="row" spacing={2} alignItems="center" sx={{ minWidth: 0 }}>
                <Box sx={{ width: 32, height: 32, bgcolor: 'action.hover', borderRadius: 1, flexShrink: 0 }} />
                <Box sx={{ minWidth: 0 }}>
                  <Typography fontWeight={600}>{name}</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>Coming soon</Typography>
                  <Stack direction="row" spacing={1} mt={1}>
                    <Chip size="small" label={name === 'Stripe' || name === 'Notion' || name === 'GitHub' || name === 'RevenueCat' ? 'MCP' : 'Integration'} />
                  </Stack>
                </Box>
              </Stack>
            </Box>
          ))}
        </Box>
      </Box>

      {/* Your Connectors Section */}
      <Box>
        <Typography variant="h6" mb={2}>Your Connectors</Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <div style={{ height: 400, width: '100%' }}>
          <DataGrid
            getRowId={(row) => row.connector_id}
            rows={connectors}
            columns={columns}
            loading={loading}
            disableRowSelectionOnClick
            onRowClick={(params: any) => navigate(`/connectors/${params.id}`)}
          />
        </div>
      </Box>

      {/* Postgres Form Dialog */}
      {showPostgresForm && (
        <Dialog open={showPostgresForm} onClose={() => setShowPostgresForm(false)} maxWidth="md" fullWidth>
          <DialogTitle>Create Postgres Connector</DialogTitle>
          <DialogContent dividers>
            <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 3 }}>
              <Box sx={{ flex: 1 }}>
                <TextField
                  label="Connection Name"
                  placeholder="Enter a name for this connection"
                  fullWidth
                  margin="normal"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                />
                <TextField
                  label="user"
                  placeholder="Enter your user"
                  fullWidth
                  margin="normal"
                  value={form.user}
                  onChange={e => setForm(f => ({ ...f, user: e.target.value }))}
                  required
                />
                <TextField
                  label="password"
                  type="password"
                  placeholder="Enter your password"
                  fullWidth
                  margin="normal"
                  value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  required
                />
                <TextField
                  label="host"
                  placeholder="Enter your host"
                  fullWidth
                  margin="normal"
                  value={form.host}
                  onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
                  required
                />
                <TextField
                  label="port"
                  type="number"
                  placeholder="Enter your port"
                  fullWidth
                  margin="normal"
                  value={form.port}
                  onChange={e => setForm(f => ({ ...f, port: e.target.value }))}
                />
                <TextField
                  label="database"
                  placeholder="Enter your database"
                  fullWidth
                  margin="normal"
                  value={form.database}
                  onChange={e => setForm(f => ({ ...f, database: e.target.value }))}
                  required
                />
                <TextField
                  select
                  label="MFA_TYPE"
                  fullWidth
                  margin="normal"
                  value={form.mfa_type}
                  onChange={e => setForm(f => ({ ...f, mfa_type: e.target.value }))}
                >
                  <MenuItem value="">None</MenuItem>
                  <MenuItem value="sms">SMS</MenuItem>
                  <MenuItem value="totp">TOTP</MenuItem>
                </TextField>
                {addErr && <Alert severity="error" sx={{ mt: 1 }}>{addErr}</Alert>}
              </Box>
              <Box sx={{ flex: 1, minWidth: 260 }}>
                <Box sx={{ p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
                  <Stack alignItems="center" spacing={1}>
                    <PostgresSvg width={40} height={40} />
                    <Typography variant="h6">Postgres</Typography>
                  </Stack>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    Data Connectors allow you to connect to data sources like Postgres by securely providing your
                    credentials to the system. Once a connector is enabled, it can be used contextually across interactions.
                  </Typography>
                  <Stack spacing={1} sx={{ mt: 2 }}>
                    <Link href="#" target="_blank" rel="noreferrer">Read the Documentation</Link>
                    <Link href="#" target="_blank" rel="noreferrer">Security & Trust Center</Link>
                  </Stack>
                </Box>
              </Box>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowPostgresForm(false)} disabled={addLoading}>Cancel</Button>
            <LoadingButton onClick={handleAddConnector} loading={addLoading} variant="contained">Add Connection</LoadingButton>
          </DialogActions>
        </Dialog>
      )}
    </Box>
  );
}
