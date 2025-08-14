import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Button, Typography, Alert, CircularProgress, Chip, Dialog, DialogTitle, DialogContent, DialogActions, List, ListItem, ListItemIcon, ListItemText, Checkbox, Stack, Tabs, Tab, Tooltip, TextField, MenuItem,
  Table, TableHead, TableRow, TableCell, TableBody
} from '@mui/material';
import JsonView from 'react18-json-view';
import 'react18-json-view/src/style.css';
import { SnackbarContext } from '../ui/SnackbarProvider';
// Alignments only; no Grid needed here
import { buildApiUrl } from '../config';

const API_URL = buildApiUrl('');

function redactConfig(config: any) {
  if (!config) return {};
  const redacted = { ...config };
  if (redacted.password) redacted.password = '••••••';
  if (redacted.client_secret) redacted.client_secret = '••••••';
  return redacted;
}

interface GoogleDriveFile {
  id: string;
  name: string;
  mimeType: string;
}

export default function ConnectorDetailPage() {
  const { connectorId } = useParams();
  const navigate = useNavigate();
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<any>(null);
const [schema, setSchema] = useState<any>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [tab, setTab] = useState(0);

  // Google Drive file picker states
  // 'drive' | 'postgres' | false
  const [selectModalOpen, setSelectModalOpen] = useState<false | 'drive' | 'postgres'>(false);
  const [driveFiles, setDriveFiles] = useState<GoogleDriveFile[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesError, setFilesError] = useState<string | null>(null);
  const [savingSelection, setSavingSelection] = useState(false);
  const [selectedDriveRows, setSelectedDriveRows] = useState<GoogleDriveFile[]>([]);
  const [selectedTableRows, setSelectedTableRows] = useState<string[]>([]);
const [retesting, setRetesting] = useState(false);
const [retestMessage, setRetestMessage] = useState<string | null>(null);
const [fetchingSchema, setFetchingSchema] = useState(false);
const [schemaMessage, setSchemaMessage] = useState<string | null>(null);
  const [schemaModalOpen, setSchemaModalOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<boolean | number>(2);
  const { notify } = React.useContext(SnackbarContext);

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
    if (tenantId && connectorId) fetchDetail();
    // eslint-disable-next-line
  }, [tenantId, connectorId]);

  // Auto-load full schema when switching to Schema tab
  useEffect(() => {
    const loadSchemaIfNeeded = async () => {
      if (tab !== 2) return;
      if (!tenantId || !connectorId) return;
      const schemaId = data?.schema?.schema_id;
      // If we already have raw_schema in state or in data, no need to fetch
      if (!schemaId || schema?.raw_schema || data?.schema?.raw_schema) return;
      try {
        setSchemaLoading(true);
        setSchemaError(null);
        const token = window.localStorage.getItem('klaris_jwt');
        const resp = await fetch(
          `${API_URL}/tenants/${tenantId}/connectors/${connectorId}/schemas/${schemaId}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (!resp.ok) {
          const result = await resp.json();
          throw new Error(result?.detail || 'Failed to fetch schema');
        }
        const result = await resp.json();
        setSchema(result);
      } catch (err: any) {
        setSchemaError(err.message || 'Failed to fetch schema');
      } finally {
        setSchemaLoading(false);
      }
    };
    loadSchemaIfNeeded();
    // eslint-disable-next-line
  }, [tab, tenantId, connectorId, data?.schema?.schema_id]);

  const fetchDetail = async () => {
    if (!tenantId || !connectorId) return;
    setLoading(true);
    setError(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      // Fetch all connectors, find ours (can optimize backend for /connectors/{id} as well)
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error('Could not fetch connector');
      const result = await resp.json();
      const found = (result.connectors || []).find((c: any) => c.connector_id === connectorId);
      if (!found) throw new Error('Connector not found');
      setData(found);
      if (found.schema && found.schema.schema_id) {
        // Optionally: fetch full schema details, for now use preview
        setSchema(found.schema);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch connector');
    } finally {
      setLoading(false);
    }
  };

  const handleRetest = async () => {
    if (!tenantId || !connectorId) return;
    setRetesting(true);
    setRetestMessage(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors/${connectorId}/retest`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.error || 'Failed to re-test connection');
      setRetestMessage('Connection and schema fetch successful.');
      fetchDetail();
    } catch (err: any) {
      setRetestMessage(err.message || 'Failed to re-test');
    } finally {
      setRetesting(false);
    }
  };

  const handleFetchSchema = async () => {
    if (!tenantId || !connectorId) return;
    setFetchingSchema(true);
    setSchemaMessage(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      // For refresh: use filtered fetch (respect saved selection)
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors/${connectorId}/fetch-schema`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Failed to fetch schema');
      const pretty = { raw_schema: result.schema, fetched_at: result.fetched_at };
      setSchema(pretty);
      setData((d: any) => ({ ...(d || {}), schema: pretty, last_schema_fetch: result.fetched_at }));
      setSchemaMessage('Schema fetched successfully');
      fetchDetail(); // update display
    } catch (err: any) {
      setSchemaMessage(err.message || 'Failed to fetch schema');
    } finally {
      setFetchingSchema(false);
    }
  };

  // Fetch Google Drive files for the picker
  async function fetchDriveFiles() {
    if (!tenantId || !connectorId) return;
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(
        `${API_URL}/tenants/${tenantId}/connectors/${connectorId}/google-drive-files`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!resp.ok) throw new Error('Could not fetch Google Drive files');
      const result = await resp.json();
      setDriveFiles(result || []);
      setSelectedIds(data?.connector_metadata?.selected_drive_file_ids || []);
      try {
        const sel = (data?.connector_metadata?.selected_drive_file_ids || []) as string[];
        setSelectedDriveRows((result || []).filter((f: any) => sel.includes(f.id)));
      } catch {}
    } catch (err: any) {
      setFilesError(err.message || 'Failed to fetch files');
    } finally {
      setFilesLoading(false);
    }
  }

  // Prepare selection summaries when the Select tab is active
  useEffect(() => {
    if (tab !== 1) return;
    if (!data) return;
    if (data.type === 'google_drive') {
      const sel = data?.connector_metadata?.selected_drive_file_ids || [];
      setSelectedIds(sel);
      if (!driveFiles.length) {
        setFilesLoading(true);
        fetchDriveFiles();
      } else {
        setSelectedDriveRows(driveFiles.filter((f) => sel.includes(f.id)));
      }
    } else if (data.type === 'postgres') {
      const names = data?.connector_metadata?.selected_table_names || [];
      setSelectedTableRows(names);
    }
    // eslint-disable-next-line
  }, [tab, data, driveFiles.length]);

  return (
    <Box sx={{ width: '100%', py: 1 }}>
      {loading ? <CircularProgress /> : error ? <Alert severity="error">{error}</Alert> : (
        <Box>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 1 }}>
            <Tab label="Overview" />
            <Tab label={data.type === 'postgres' ? 'Select Tables' : 'Select Files'} />
            <Tab label="Schema" />
          </Tabs>

          {tab === 0 && (
            <Box>
              {/* Meta grid */}
              <Box sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(4, minmax(0, 1fr))' },
                gap: 1,
                mb: 1,
              }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">ID</Typography>
                  <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>{data.connector_id}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Type</Typography>
                  <Typography variant="body2">{data.type}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Status</Typography>
                  <Chip size="small" label={data.status} color={data.status === 'active' ? 'success' : 'error'} />
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Last Schema Fetch</Typography>
                  <Typography variant="body2">
                    {data.last_schema_fetch ? (
                      <Tooltip title={new Date(data.last_schema_fetch).toLocaleString()}>
                        <span>{new Date(data.last_schema_fetch).toLocaleString()}</span>
                      </Tooltip>
                    ) : 'Never'}
                  </Typography>
                </Box>
              </Box>
              <Typography fontWeight="bold" sx={{ mb: 0.5 }}>Connector Config</Typography>
              <Box sx={{
                bgcolor: 'background.default',
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                overflowX: 'auto',
              }}>
                <pre style={{ margin: 0, padding: 12 }}>
{`${JSON.stringify(redactConfig(data.config), null, 2)}`}
                </pre>
              </Box>
              {data.error_message && (
                <Alert severity="warning" sx={{ mt: 1 }}>Error: {data.error_message}</Alert>
              )}
            </Box>
          )}

            {tab === 2 && (
              <Box>
                <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                  <Button variant="contained" onClick={handleFetchSchema} disabled={fetchingSchema}>
                    {fetchingSchema ? 'Refreshing…' : 'Refresh Schema'}
                  </Button>
                  <Typography variant="body2" color="text.secondary">
                    Last fetched: {data.last_schema_fetch ? new Date(data.last_schema_fetch).toLocaleString() : 'Never'}
                  </Typography>
                  <Box sx={{ flex: 1 }} />
                  <TextField
                    select
                    size="small"
                    label="Collapse"
                    value={typeof collapsed === 'number' ? String(collapsed) : collapsed ? 'all' : 'none'}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === 'all') setCollapsed(true);
                      else if (v === 'none') setCollapsed(false);
                      else setCollapsed(Number(v));
                    }}
                    sx={{ width: 140 }}
                  >
                    <MenuItem value="none">None</MenuItem>
                    <MenuItem value="1">Level 1</MenuItem>
                    <MenuItem value="2">Level 2</MenuItem>
                    <MenuItem value="3">Level 3</MenuItem>
                    <MenuItem value="all">All</MenuItem>
                  </TextField>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => {
                      const obj = schema?.raw_schema || data?.schema?.raw_schema;
                      if (!obj) return;
                      try {
                        navigator.clipboard.writeText(JSON.stringify(obj, null, 2));
                        notify('Schema copied to clipboard', 'success');
                      } catch {
                        notify('Copy failed', 'error');
                      }
                    }}
                  >
                    Copy all
                  </Button>
                </Stack>
                {(schemaMessage) && <Alert severity={schemaMessage.includes('success') ? 'success' : 'error'} sx={{ mb: 1 }}>{schemaMessage}</Alert>}
                <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, bgcolor: 'background.default', minHeight: 120 }}>
                  {schemaLoading ? (
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', py: 3 }}>
                      <CircularProgress size={24} />
                    </Box>
                  ) : schemaError ? (
                    <Alert severity="error" sx={{ m: 1 }}>{schemaError}</Alert>
                  ) : (schema?.raw_schema || data?.schema?.raw_schema) ? (
                    <Box sx={{ p: 1.5 }}>
                      <JsonView
                        src={schema?.raw_schema || data?.schema?.raw_schema}
                        theme="github"
                        collapsed={collapsed}
                        enableClipboard
                      />
                    </Box>
                  ) : (
                    <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
                      No schema available yet. Click Refresh Schema to fetch.
                    </Typography>
                  )}
                </Box>
              </Box>
            )}

            {tab === 1 && (
              <Stack direction="column" gap={1} mt={1}>
              {data.type === 'google_drive' && (
                <>
                  <Stack direction="row" gap={1} alignItems="center">
                    <Button
                      variant="outlined"
                      onClick={() => {
                        setSelectModalOpen('drive');
                        setFilesLoading(true);
                        setFilesError(null);
                        fetchDriveFiles();
                      }}
                    >
                      {data?.connector_metadata?.selected_drive_file_ids?.length
                        ? 'Edit Selection'
                        : 'Select Google Drive Files/Folders'}
                    </Button>
                    {data?.connector_metadata?.selected_drive_file_ids?.length > 0 && (
                      <Chip label={`${data.connector_metadata.selected_drive_file_ids.length} items`} color="info" size="small" />
                    )}
                  </Stack>
                  <Box>
                    <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Selected Files</Typography>
                    {filesLoading ? (
                      <CircularProgress size={22} />
                    ) : (selectedDriveRows.length > 0 ? (
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Name</TableCell>
                            <TableCell>Type</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {selectedDriveRows.map((f) => (
                            <TableRow key={f.id}>
                              <TableCell>{f.name}</TableCell>
                              <TableCell>{f.mimeType}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Typography variant="body2" color="text.secondary">No files selected.</Typography>
                    ))}
                  </Box>
                </>
              )}

              {/* Postgres table selection support */}
              {data.type === 'postgres' && (
                <>
                  <Stack direction="row" gap={1} alignItems="center">
                    <Button
                      variant="outlined"
                      onClick={async () => {
                        // Always fetch latest full table list from backend, do not use cached schema
                        setSelectModalOpen('postgres');
                        try {
                          setFilesLoading(true);
                          setFilesError(null);
                          const token = window.localStorage.getItem('klaris_jwt');
                          const resp = await fetch(
                            `${API_URL}/tenants/${tenantId}/connectors/${data.connector_id}/fetch-schema?full=true`,
                            { method: 'POST', headers: { Authorization: `Bearer ${token}` } }
                          );
                          const result = await resp.json();
                          let tables: any[] = [];
                          if (result?.schema?.tables) tables = result.schema.tables;
                          else if (result?.files) tables = result.files; // fallback to files
                          setDriveFiles((tables || []).map((t: any) => ({ id: t.table, name: t.table, mimeType: t.schema })));
                          setSelectedIds(data?.connector_metadata?.selected_table_names || []);
                        } catch (err: any) {
                          setFilesError('Failed to fetch tables');
                        } finally {
                          setFilesLoading(false);
                        }
                      }}
                    >
                      {data?.connector_metadata?.selected_table_names?.length ? 'Edit Selection' : 'Select Postgres Tables'}
                    </Button>
                    {data?.connector_metadata?.selected_table_names?.length > 0 && (
                      <Chip label={`${data.connector_metadata.selected_table_names.length} tables`} color="info" size="small" />
                    )}
                  </Stack>
                  <Box>
                    <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Selected Tables</Typography>
                    {selectedTableRows.length > 0 ? (
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Table</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {selectedTableRows.map((t) => (
                            <TableRow key={t}>
                              <TableCell>{t}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : (
                      <Typography variant="body2" color="text.secondary">No tables selected.</Typography>
                    )}
                  </Box>
                </>
              )}
              {/* Retest and View Schema removed per request */}
              </Stack>
            )}
          {(retestMessage) && <Alert severity={retestMessage.includes('success') ? 'success' : 'error'} sx={{ mt: 2 }}>{retestMessage}</Alert>}
        </Box>
      )}
      {/* Schema modal removed in favor of inline view */}
      {/* Google Drive File/Folder Picker Modal */}
      <Dialog open={!!selectModalOpen} onClose={() => setSelectModalOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectModalOpen === 'drive' ? 'Select Google Drive Files/Folders' : 'Select Postgres Tables'}
        </DialogTitle>
        <DialogContent>
          {filesLoading ? (
            <Box display="flex" justifyContent="center">
              <CircularProgress />
            </Box>
          ) : filesError ? (
            <Alert severity="error">{filesError}</Alert>
          ) : (
            <List>
              {[
                ...selectedIds
                  .map(selId => driveFiles.find(f => f.id === selId))
                  .filter(Boolean),
                ...driveFiles.filter(f => !selectedIds.includes(f.id)),
              ].map((f: any) => f && (
                <ListItem
                  key={f.id}
                  dense
                  component="button"
                  onClick={() => {
                    setSelectedIds(selectedIds.includes(f.id)
                      ? selectedIds.filter(id => id !== f.id)
                      : [...selectedIds, f.id]);
                  }}
                >
                  <ListItemIcon>
                    <Checkbox
                      edge="start"
                      checked={selectedIds.includes(f.id)}
                      tabIndex={-1}
                      disableRipple
                    />
                  </ListItemIcon>
                  <ListItemText
                    primary={f.name}
                    secondary={selectModalOpen === 'drive' ? f.mimeType : undefined}
                  />
                </ListItem>
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectModalOpen(false)}>Cancel</Button>
          <Button
            onClick={async () => {
              setSavingSelection(true);
              try {
                const token = window.localStorage.getItem('klaris_jwt');
                const patchBody = selectModalOpen === 'drive'
                  ? { connector_metadata: { selected_drive_file_ids: selectedIds } }
                  : { connector_metadata: { selected_table_names: selectedIds } };
                const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors/${connectorId}`,
                  {
                    method: 'PATCH',
                    headers: {
                      'Authorization': `Bearer ${token}`,
                      'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(patchBody),
                  }
                );
                if (!resp.ok) throw new Error('Failed to save selection');
                    await fetchDetail();
                    // Refresh inline summaries
                    if (selectModalOpen === 'drive') {
                      setSelectedDriveRows(driveFiles.filter((f) => selectedIds.includes(f.id)));
                    } else {
                      setSelectedTableRows([...(selectedIds as string[])]);
                    }
                setSelectModalOpen(false);
              } catch (err: any) {
                setFilesError(err.message || 'Failed to save');
              }
              setSavingSelection(false);
            }}
            disabled={savingSelection || filesLoading}
            variant="contained"
            color="primary"
          >
            {savingSelection ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
