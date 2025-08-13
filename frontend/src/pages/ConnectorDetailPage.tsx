import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Button, Card, CardContent, Typography, Alert, CircularProgress, Chip, Dialog, DialogTitle, DialogContent, DialogActions, List, ListItem, ListItemIcon, ListItemText, Checkbox, Stack
} from '@mui/material';
import Grid from '@mui/material/Grid';
import ReactJson from 'react-json-view';
// Divider imported only once below
import Divider from '@mui/material/Divider';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

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

  // Google Drive file picker states
  const [selectModalOpen, setSelectModalOpen] = useState(false);
  const [driveFiles, setDriveFiles] = useState<GoogleDriveFile[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesError, setFilesError] = useState<string | null>(null);
  const [savingSelection, setSavingSelection] = useState(false);
const [retesting, setRetesting] = useState(false);
const [retestMessage, setRetestMessage] = useState<string | null>(null);
const [fetchingSchema, setFetchingSchema] = useState(false);
const [schemaMessage, setSchemaMessage] = useState<string | null>(null);
const [schemaModalOpen, setSchemaModalOpen] = useState(false);

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
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors/${connectorId}/fetch-schema`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Failed to fetch schema');
      setSchema({ raw_schema: result.schema, fetched_at: result.fetched_at });
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
    } catch (err: any) {
      setFilesError(err.message || 'Failed to fetch files');
    } finally {
      setFilesLoading(false);
    }
  }

  return (
    <Box sx={{ mt: 2, maxWidth: 800, mx: 'auto' }}>
      <Button
        variant="outlined"
        size="small"
        sx={{ mb: 2 }}
        onClick={() => navigate('/connectors')}
        color="secondary"
      >
        Back to Connectors
      </Button>
      {loading ? <CircularProgress /> : error ? <Alert severity="error">{error}</Alert> : (
        <Card>
          <CardContent>
            {/* Details Section */}
            <Typography variant="h5" mb={1}>
              Connector Detail
              <Chip label={data.status} color={data.status === 'active' ? 'success' : 'error'} sx={{ ml: 2 }} />
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={1}>ID: {data.connector_id}</Typography>
            <Typography variant="body2" mb={1}><b>Type:</b> {data.type}</Typography>
            <Typography variant="body2" mb={1}><b>Last Schema Fetch:</b> {data.last_schema_fetch ? new Date(data.last_schema_fetch).toLocaleString() : 'Never'}</Typography>
            {data.error_message && (
              <Alert severity="warning" sx={{ mt: 1 }}>Error: {data.error_message}</Alert>
            )}

            <Divider sx={{ my: 2 }} />
            {/* Connector Config Section */}
            <Typography fontWeight="bold">Connector Config:</Typography>
            <pre style={{ background: '#f6f6f6', padding: 10, borderRadius: 4, marginBottom: 0 }}>
              {JSON.stringify(redactConfig(data.config), null, 2)}
            </pre>
            <Divider sx={{ my: 2 }} />
            {/* Canonical Schema Section */}
            <Box>
              <Typography fontWeight="bold" mb={1}>Canonical Schema</Typography>
              {data.last_schema_fetch ? (
                <Box>
                  <Typography variant="caption" color="text.secondary">Fetched: {data.last_schema_fetch ? new Date(data.last_schema_fetch).toLocaleString() : ''}</Typography>
                </Box>
              ) : (
                <Typography>No schema available yet.</Typography>
              )}
            </Box>
            <Divider sx={{ my: 3 }} />
            {/* Action Bar Section */}
            <Stack direction="row" gap={2} mt={2} alignItems="center" flexWrap="wrap">
              {data.type === 'google_drive' && (
                <>
                  <Button
                    variant="outlined"
                    onClick={() => {
                      setSelectModalOpen(true);
                      setFilesLoading(true);
                      setFilesError(null);
                      fetchDriveFiles();
                    }}
                  >
                    {data?.connector_metadata?.selected_drive_file_ids?.length
                      ? `Edit Google Drive Selection (${data.connector_metadata.selected_drive_file_ids.length} selected)`
                      : 'Select Google Drive Files/Folders'}
                  </Button>
                  {data?.connector_metadata?.selected_drive_file_ids?.length > 0 && (
                    <Chip
                      label={`${data.connector_metadata.selected_drive_file_ids.length} items selected`}
                      color="info"
                      sx={{ ml: 1 }}
                    />
                  )}
                </>
              )}
              <Button variant="contained" color="primary" onClick={handleFetchSchema} disabled={fetchingSchema}>
                {fetchingSchema ? 'Fetching Schema...' : 'Fetch Schema'}
              </Button>
              <Button variant="outlined" onClick={handleRetest} disabled={retesting}>Re-test Connector</Button>
              {retesting && <CircularProgress size={18} sx={{ ml: 1 }} />}
              <Button
                onClick={async () => {
                  // Fetch the canonical schema using the backend endpoint
                  if (!data?.schema?.schema_id) {
                    setSchemaError('No schema available.');
                    setSchemaModalOpen(true);
                    return;
                  }
                  setSchemaLoading(true);
                  setSchemaError(null);
                  setSchema(null);
                  setSchemaModalOpen(true);
                  try {
                    const token = window.localStorage.getItem('klaris_jwt');
                    const resp = await fetch(
                      `${API_URL}/tenants/${tenantId}/connectors/${data.connector_id}/schemas/${data.schema.schema_id}`,
                      {
                        headers: { Authorization: `Bearer ${token}` },
                      }
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
                }}
                variant="outlined"
              >
                View Schema
              </Button>
            </Stack>
            {(schemaMessage || retestMessage) && <Alert severity={(schemaMessage?.includes('success') || retestMessage?.includes('success')) ? 'success' : 'error'} sx={{ mt: 2 }}>{schemaMessage || retestMessage}</Alert>}
          </CardContent>
        </Card>
      )}
      {/* Modal to view schema */}
      <Dialog open={schemaModalOpen} onClose={() => setSchemaModalOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Schema Preview</DialogTitle>
        <DialogContent>
          <Box>
            {schemaLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', my: 2 }}>
                <CircularProgress />
              </Box>
            ) : schemaError ? (
              <Alert severity="error">{schemaError}</Alert>
            ) : schema ? (
              <ReactJson
                src={schema.raw_schema || schema}
                name={false}
                iconStyle="circle"
                enableClipboard
                displayDataTypes={false}
                collapsed={2}
                style={{ fontSize: 15 }}
              />
            ) : (
              <Typography variant="body2" color="text.secondary">No schema data.</Typography>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSchemaModalOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
      {/* Google Drive File/Folder Picker Modal */}
      <Dialog open={selectModalOpen} onClose={() => setSelectModalOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Select Google Drive Files/Folders</DialogTitle>
        <DialogContent>
          {filesLoading ? (
            <Box display="flex" justifyContent="center">
              <CircularProgress />
            </Box>
          ) : filesError ? (
            <Alert severity="error">{filesError}</Alert>
          ) : (
            <List>
              {/* Selected files on top */}
              {[
                // Selected (in the order of selectedIds)
                ...selectedIds
                  .map(selId => driveFiles.find(f => f.id === selId))
                  .filter(Boolean),
                // Unselected
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
                  <ListItemText primary={f.name} secondary={f.mimeType} />
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
                const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors/${connectorId}`,
                  {
                    method: 'PATCH',
                    headers: {
                      'Authorization': `Bearer ${token}`,
                      'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                      connector_metadata: { selected_drive_file_ids: selectedIds },
                    }),
                  }
                );
                if (!resp.ok) throw new Error('Failed to save selection');
                // Refetch connector details to get the updated connector_metadata
                await fetchDetail();
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
