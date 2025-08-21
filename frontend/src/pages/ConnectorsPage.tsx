import React, { useEffect, useState } from 'react';
import {
  Box, Button, Typography, Alert, TextField, MenuItem, Stack, Chip, Dialog, DialogTitle, DialogContent, DialogActions, Link, IconButton
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
// Avoid Grid to reduce typings complexity in modal; simple Box layout instead
import { LoadingButton } from '@mui/lab';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { useNavigate } from 'react-router-dom';
import { buildApiUrl } from '../config';
import { ReactComponent as GoogleDriveSvg } from '../assets/connectors/google-drive.svg';
import { ReactComponent as PostgresSvg } from '../assets/connectors/postgres.svg';
import Tooltip from '@mui/material/Tooltip';
import { formatLocalDatetime } from '../utils/date';

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
  const [showGoogleDriveModal, setShowGoogleDriveModal] = useState(false);
  const [googleDriveName, setGoogleDriveName] = useState("");
  const [googleDriveErr, setGoogleDriveErr] = useState<string | null>(null);
  // Removed tabs - now showing new connector by default with Your Connectors below

  // Delete states
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [connectorToDelete, setConnectorToDelete] = useState<Connector | null>(null);
  const [deleting, setDeleting] = useState(false);

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

  const handleDeleteConnector = async () => {
    if (!connectorToDelete || !tenantId) return;
    setDeleting(true);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors/${connectorToDelete.connector_id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!resp.ok) {
        const data = await resp.json();
        throw new Error(data?.error || 'Failed to delete connector');
      }
      // Refresh the connectors list
      await fetchConnectors();
      setDeleteDialogOpen(false);
      setConnectorToDelete(null);
    } catch (err: any) {
      setError(err.message || 'Failed to delete connector');
    } finally {
      setDeleting(false);
    }
  };

  const columns: GridColDef[] = [
    { 
      field: 'name', 
      headerName: 'Name', 
      flex: 1,
      minWidth: 200,
      renderCell: (params: any) => (
        <Tooltip title={params.value || `${params.row.type} Connector`}>
          <Box sx={{ 
            overflow: 'hidden', 
            textOverflow: 'ellipsis', 
            whiteSpace: 'nowrap',
            width: '100%'
          }}>
            {params.value || `${params.row.type} Connector`}
          </Box>
        </Tooltip>
      )
    },
    { 
      field: 'type', 
      headerName: 'Type', 
      width: 110,
      renderCell: (params: any) => (
        <Box sx={{ textTransform: 'capitalize' }}>
          {params.value?.replace('_', ' ') || '—'}
        </Box>
      )
    },
    { 
      field: 'status', 
      headerName: 'Status', 
      width: 90, 
      renderCell: (params: any) => (
        <Chip 
          label={params.value} 
          color={params.value === 'active' ? 'success' : params.value === 'failed' ? 'error' : 'default'} 
          size="small" 
        />
      ) 
    },
    {
      field: 'created_at',
      headerName: 'Created',
      width: 180,
      renderCell: (params: any) => params.value ? (
        <Tooltip title={formatLocalDatetime(params.value)}>
          <Chip size="small" variant="outlined" label={formatLocalDatetime(params.value)} />
        </Tooltip>
      ) : <Chip size="small" variant="outlined" label="—" />, 
    },
    {
      field: 'last_schema_fetch',
      headerName: 'Last Schema Fetch',
      width: 180,
      renderCell: (params) => params.value ? (
        <Tooltip title={formatLocalDatetime(params.value)}>
          <Chip size="small" variant="outlined" label={formatLocalDatetime(params.value)} />
        </Tooltip>
      ) : <Chip size="small" variant="outlined" label="Never" />, 
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 70,
      sortable: false,
  renderCell: (params: { row: Connector }) => (
        <IconButton
          size="small"
          onClick={(e) => {
            (e as React.MouseEvent).stopPropagation(); // Prevent row click navigation
            setConnectorToDelete(params.row);
            setDeleteDialogOpen(true);
          }}
          color="error"
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      ),
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
            onClick={() => setShowGoogleDriveModal(true)}
          >
      {/* Google Drive Connector Name Modal */}
      <Dialog open={showGoogleDriveModal} onClose={() => setShowGoogleDriveModal(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Google Drive Connector</DialogTitle>
        <DialogContent>
          <TextField
            label="Connector Name"
            placeholder="Enter a name for this connection"
            fullWidth
            margin="normal"
            value={googleDriveName}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setGoogleDriveName(e.target.value)}
            required
          />
          {googleDriveErr && <Alert severity="error" sx={{ mt: 1 }}>{googleDriveErr}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowGoogleDriveModal(false)}>Cancel</Button>
          <LoadingButton
            onClick={() => {
              setGoogleDriveErr(null);
              if (!googleDriveName.trim()) {
                setGoogleDriveErr("Connector name is required.");
                return;
              }
              if (!tenantId) {
                setGoogleDriveErr("Tenant not found.");
                return;
              }
              // Optionally: Save the connector name in localStorage or pass as query param
              // For now, pass as query param
              const url = `${API_URL}/connectors/google-drive/authorize?tenant_id=${tenantId}&name=${encodeURIComponent(googleDriveName.trim())}`;
              window.location.href = url;
            }}
            variant="contained"
          >
            Proceed to OAuth
          </LoadingButton>
        </DialogActions>
      </Dialog>
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
      <Box sx={{ mt: 4 }}>
        <Typography variant="h6" mb={2}>Your Connectors</Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Box sx={{ width: '100%', minWidth: 0 }}>
          <DataGrid
            getRowId={(row: Connector) => row.connector_id}
            rows={connectors}
            columns={columns.map(col => ({ ...col, align: 'left', headerAlign: 'left' }))}
            loading={loading}
            disableRowSelectionOnClick
            onRowClick={(params: any) => navigate(`/connectors/${params.id}`)}
            autoHeight
            initialState={{
              pagination: { paginationModel: { pageSize: 10 } }
            }}
            pageSizeOptions={[10, 25, 50, 100]}
            sx={{ '& .MuiDataGrid-columnHeaders': { backgroundColor: 'background.paper' }, fontSize: 14 }}
          />
        </Box>
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
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm((f: typeof form) => ({ ...f, name: e.target.value }))}
                />
                <TextField
                  label="user"
                  placeholder="Enter your user"
                  fullWidth
                  margin="normal"
                  value={form.user}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm((f: typeof form) => ({ ...f, user: e.target.value }))}
                  required
                />
                <TextField
                  label="password"
                  type="password"
                  placeholder="Enter your password"
                  fullWidth
                  margin="normal"
                  value={form.password}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm((f: typeof form) => ({ ...f, password: e.target.value }))}
                  required
                />
                <TextField
                  label="host"
                  placeholder="Enter your host"
                  fullWidth
                  margin="normal"
                  value={form.host}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm((f: typeof form) => ({ ...f, host: e.target.value }))}
                  required
                />
                <TextField
                  label="port"
                  type="number"
                  placeholder="Enter your port"
                  fullWidth
                  margin="normal"
                  value={form.port}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm((f: typeof form) => ({ ...f, port: e.target.value }))}
                />
                <TextField
                  label="database"
                  placeholder="Enter your database"
                  fullWidth
                  margin="normal"
                  value={form.database}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm((f: typeof form) => ({ ...f, database: e.target.value }))}
                  required
                />
                <TextField
                  select
                  label="MFA_TYPE"
                  fullWidth
                  margin="normal"
                  value={form.mfa_type}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm((f: typeof form) => ({ ...f, mfa_type: e.target.value }))}
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

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => !deleting && setDeleteDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Delete Connector</DialogTitle>
        <DialogContent>
          <Typography variant="body1" sx={{ mb: 2 }}>
            Are you sure you want to delete the connector "{connectorToDelete?.name || `${connectorToDelete?.type} Connector`}"?
          </Typography>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This action cannot be undone. All schemas and configuration data for this connector will be permanently deleted.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)} disabled={deleting}>Cancel</Button>
          <LoadingButton 
            onClick={handleDeleteConnector}
            loading={deleting}
            variant="contained"
            color="error"
          >
            Delete
          </LoadingButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
