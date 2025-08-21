import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Button, Typography, Alert, CircularProgress, Chip, Dialog, DialogTitle, DialogContent, DialogActions, List, ListItem, ListItemIcon, ListItemText, Checkbox, Stack, Tabs, Tab, Tooltip, TextField, MenuItem,
  Table, TableHead, TableRow, TableCell, TableBody, IconButton
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import JsonView from 'react18-json-view';
import 'react18-json-view/src/style.css';
import { SnackbarContext } from '../ui/SnackbarProvider';
// Alignments only; no Grid needed here
import { buildApiUrl, config } from '../config';
import GoogleDrivePicker, { GoogleDriveFile } from '../components/GoogleDrivePicker';
import { GOOGLE_DRIVE_MIME_TYPES } from '../utils/googlePicker';
import { formatLocalDatetime } from '../utils/date';

const API_URL = buildApiUrl('');

function redactConfig(config: any) {
  if (!config) return {};
  const redacted = { ...config };
  if (redacted.password) redacted.password = '••••••';
  if (redacted.client_secret) redacted.client_secret = '••••••';
  return redacted;
}


export default function ConnectorDetailPage() {
  const { connectorId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isSetupMode = searchParams.get('setup') === 'true';
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
  
  // Setup flow states
  const [connectorName, setConnectorName] = useState('');
  const [namingStep, setNamingStep] = useState(false);
  const [autoFileSelection, setAutoFileSelection] = useState(false);
  const [autoSchemaFetch, setAutoSchemaFetch] = useState(false);

  // Delete states
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  // Setup flow: automatically start naming step for new Google Drive connectors
  useEffect(() => {
    if (isSetupMode && data && data.type === 'google_drive' && !data.name) {
      setNamingStep(true);
    }
  }, [isSetupMode, data]);

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
      setAutoSchemaFetch(false); // Reset auto-fetch flag
      fetchDetail(); // update display
    } catch (err: any) {
      setSchemaMessage(err.message || 'Failed to fetch schema');
      setAutoSchemaFetch(false);
    } finally {
      setFetchingSchema(false);
    }
  };

  const handleSaveName = async () => {
    if (!tenantId || !connectorId || !connectorName.trim()) return;
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors/${connectorId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: connectorName.trim() }),
      });
      if (!resp.ok) throw new Error('Failed to save connector name');
      await fetchDetail();
      setNamingStep(false);
      // Auto-open file selection for Google Drive
      if (data?.type === 'google_drive') {
        setAutoFileSelection(true);
        setSelectModalOpen('drive');
        setFilesLoading(true);
        setFilesError(null);
        fetchDriveFiles();
      }
    } catch (err: any) {
      notify(err.message || 'Failed to save name', 'error');
    }
  };

  const handleDeleteConnector = async () => {
    if (!tenantId || !connectorId) return;
    setDeleting(true);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors/${connectorId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!resp.ok) {
        const errorData = await resp.json();
        throw new Error(errorData?.error || 'Failed to delete connector');
      }
      // Navigate back to connectors list
      navigate('/connectors');
      notify('Connector deleted successfully', 'success');
    } catch (err: any) {
      notify(err.message || 'Failed to delete connector', 'error');
    } finally {
      setDeleting(false);
      setDeleteDialogOpen(false);
    }
  };

  // Fetch Google Drive files for the picker
  async function fetchDriveFiles() {
    if (!tenantId || !connectorId) return;
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(
        `${API_URL}/tenants/${tenantId}/connectors/${connectorId}/select-files`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!resp.ok) throw new Error('Could not fetch selectable items');
      const result = await resp.json();
      setDriveFiles(result || []);
      setSelectedIds(data?.connector_metadata?.selected_drive_file_ids || []);
      try {
        const sel = (data?.connector_metadata?.selected_drive_file_ids || []) as string[];
        setSelectedDriveRows((result || []).filter((f: any) => sel.includes(f.id)));
      } catch {}
    } catch (err: any) {
      setFilesError(err.message || 'Failed to fetch items');
    } finally {
      setFilesLoading(false);
    }
  }

  // Fetch Postgres tables for the picker (lightweight; no full schema)
  async function fetchPostgresTables() {
    if (!tenantId || !connectorId) return;
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(
        `${API_URL}/tenants/${tenantId}/connectors/${connectorId}/select-files`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!resp.ok) throw new Error('Could not fetch selectable items');
      const result = await resp.json();
      // The unified endpoint already returns: {id, name, mimeType}
      setDriveFiles(result || []);
      setSelectedIds(data?.connector_metadata?.selected_table_names || []);
    } catch (err: any) {
      setFilesError(err.message || 'Failed to fetch items');
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
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
            <Tabs value={tab} onChange={(_, v) => setTab(v)}>
              <Tab label="Overview" />
              <Tab label={data.type === 'postgres' ? 'Select Tables' : 'Select Files'} />
              <Tab label="Schema" />
            </Tabs>
            <Button
              variant="outlined"
              color="error"
              size="small"
              startIcon={<DeleteIcon />}
              onClick={() => setDeleteDialogOpen(true)}
              disabled={deleting}
            >
              Delete Connector
            </Button>
          </Box>

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
                  <Typography variant="body2">
                    <Chip size="small" label={data.status} color={data.status === 'active' ? 'success' : 'error'} />
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Last Schema Fetch</Typography>
                  <Typography variant="body2">
                    {data.last_schema_fetch ? (
                      <Tooltip title={formatLocalDatetime(data.last_schema_fetch)}>
                        <span>{formatLocalDatetime(data.last_schema_fetch)}</span>
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
                    Last fetched: {data.last_schema_fetch ? formatLocalDatetime(data.last_schema_fetch) : 'Never'}
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
                    {config.googleApiKey && data?.config?.oauth_access_token ? (
                      <GoogleDrivePicker
                        accessToken={data.config.oauth_access_token}
                        developerKey={config.googleApiKey}
                        onFilesSelected={async (files) => {
                          setSavingSelection(true);
                          try {
                            const token = window.localStorage.getItem('klaris_jwt');
                            const fileIds = files.map(file => file.id);
                            const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors/${connectorId}`, {
                              method: 'PATCH',
                              headers: {
                                'Authorization': `Bearer ${token}`,
                                'Content-Type': 'application/json',
                              },
                              body: JSON.stringify({
                                connector_metadata: { selected_drive_file_ids: fileIds }
                              }),
                            });
                            if (!resp.ok) throw new Error('Failed to save selection');
                            await fetchDetail();
                            notify('Files selected successfully', 'success');
                            
                            // Auto-proceed to schema discovery if in setup flow
                            if (autoFileSelection && fileIds.length > 0) {
                              setAutoFileSelection(false);
                              setAutoSchemaFetch(true);
                              setTimeout(() => {
                                handleFetchSchema();
                              }, 500);
                            }
                          } catch (err: any) {
                            notify(err.message || 'Failed to save selection', 'error');
                          } finally {
                            setSavingSelection(false);
                          }
                        }}
                        onCancel={() => {
                          console.log('Google Drive Picker cancelled');
                        }}
                        buttonText="Select Google Drive Files"
                        editButtonText="Edit Selection"
                        multiselect={true}
                        includeFolders={true}
                        mimeTypes={GOOGLE_DRIVE_MIME_TYPES.ALL_DOCUMENTS}
                        pickerTitle="Select files from Google Drive"
                        disabled={savingSelection}
                        loading={savingSelection}
                        selectedFileIds={data?.connector_metadata?.selected_drive_file_ids || []}
                        variant="outlined"
                        color="primary"
                      />
                    ) : (
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
                    )}
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
                        setSelectModalOpen('postgres');
                        setFilesLoading(true);
                        setFilesError(null);
                        fetchPostgresTables();
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
      {autoSchemaFetch && (
        <Alert severity="info" sx={{ mt: 2 }}>
          <Typography variant="body2">
            Setting up your connector... Automatically fetching schema from selected files.
          </Typography>
        </Alert>
      )}
        </Box>
      )}
      {/* Schema modal removed in favor of inline view */}
      {/* Google Drive File/Folder Picker Modal */}
      <Dialog open={!!selectModalOpen} onClose={() => setSelectModalOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectModalOpen === 'drive' ? 'Select Google Drive Files' : 'Select Postgres Tables'}
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
              ]
                // Filter out folders for Google Drive selection
                .filter((f: any) => selectModalOpen !== 'drive' || (f && f.mimeType !== 'application/vnd.google-apps.folder'))
                .map((f: any) => f && (
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
                
                // Auto-proceed to schema discovery if in setup flow
                if (autoFileSelection && selectedIds.length > 0) {
                  setAutoFileSelection(false);
                  setAutoSchemaFetch(true);
                  setTimeout(() => {
                    handleFetchSchema();
                  }, 500); // Small delay for better UX
                }
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
      
      {/* Connector Naming Dialog */}
      <Dialog open={namingStep} maxWidth="sm" fullWidth>
        <DialogTitle>Name Your Google Drive Connector</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Give your Google Drive connector a name to help you identify it later.
          </Typography>
          <TextField
            autoFocus
            label="Connector Name"
            placeholder="e.g., My Google Drive Documents"
            fullWidth
            value={connectorName}
            onChange={(e) => setConnectorName(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter' && connectorName.trim()) {
                handleSaveName();
              }
            }}
            margin="normal"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNamingStep(false)}>Skip</Button>
          <Button 
            onClick={handleSaveName}
            variant="contained"
            disabled={!connectorName.trim()}
          >
            Continue
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => !deleting && setDeleteDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Delete Connector</DialogTitle>
        <DialogContent>
          <Typography variant="body1" sx={{ mb: 2 }}>
            Are you sure you want to delete the connector "{data?.name || `${data?.type} Connector`}"?
          </Typography>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This action cannot be undone. All schemas and configuration data for this connector will be permanently deleted.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)} disabled={deleting}>Cancel</Button>
          <Button 
            onClick={handleDeleteConnector}
            variant="contained"
            color="error"
            disabled={deleting}
          >
            {deleting ? 'Deleting...' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
