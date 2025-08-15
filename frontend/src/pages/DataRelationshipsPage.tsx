import React from 'react';
import { Box, Typography, Accordion, AccordionSummary, AccordionDetails, Button, CircularProgress, Alert, Stack, Checkbox, List, ListItem, ListItemText, Dialog, DialogTitle, DialogContent, DialogActions, Table, TableHead, TableRow, TableCell, TableBody } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import JsonView from 'react18-json-view';
import 'react18-json-view/src/style.css';
import { buildApiUrl } from '../config';

const API_URL = buildApiUrl('');

export default function DataRelationshipsPage() {
  const [tenantId, setTenantId] = React.useState<string | null>(null);
  const [connectors, setConnectors] = React.useState<any[]>([]);
  const [selectedConnectorIds, setSelectedConnectorIds] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [schemaModal, setSchemaModal] = React.useState<{ open: boolean; entities?: any[] }>(() => ({ open: false }));
  const [reviewLoading, setReviewLoading] = React.useState(false);
  const [reviewError, setReviewError] = React.useState<string | null>(null);
  const [reviewData, setReviewData] = React.useState<any | null>(null);
  const [canonicalSaving, setCanonicalSaving] = React.useState(false);
  const [canonicalMessage, setCanonicalMessage] = React.useState<string | null>(null);
  const [savedCanonical, setSavedCanonical] = React.useState<any | null>(null);
  const [savedCanonicalVersion, setSavedCanonicalVersion] = React.useState<number | null>(null);
  const [savedCanonicalLoading, setSavedCanonicalLoading] = React.useState(false);

  React.useEffect(() => {
    const tStr = window.localStorage.getItem('klaris_tenant');
    if (!tStr) return;
    const t = JSON.parse(tStr);
    setTenantId(t.tenant_id);
  }, []);

  React.useEffect(() => {
    async function load() {
      if (!tenantId) return;
      setLoading(true); setError(null);
      try {
        const token = window.localStorage.getItem('klaris_jwt');
        const resp = await fetch(`${API_URL}/tenants/${tenantId}/connectors`, { headers: { Authorization: `Bearer ${token}` } });
        if (!resp.ok) throw new Error('Failed to load connectors');
        const result = await resp.json();
        const list = (result.connectors || []).filter((c: any) => c.status === 'active');
        setConnectors(list);
        // Default: all ACTIVE preselected
        setSelectedConnectorIds(list.map((c: any) => c.connector_id));
      } catch (e: any) {
        setError(e.message || 'Failed to load');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [tenantId]);

  const runEnrich = async () => {
    if (!tenantId || selectedConnectorIds.length === 0) return;
    setReviewLoading(true); setReviewError(null); setReviewData(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const body = { connector_ids: selectedConnectorIds, options: { confidence_threshold: 0.6 } };
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/relationships/reviews`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Enrich failed');
      setReviewData(result);
    } catch (e: any) {
      setReviewError(e.message || 'Failed to run enrichment');
    } finally {
      setReviewLoading(false);
    }
  };

  function extractEntities(obj: any): any[] {
    if (!obj) return [];
    // Stored DB shape may be either { schema: {...} } or direct
    const root = obj.schema ?? obj;
    const entities = root?.entities;
    return Array.isArray(entities) ? entities : [];
  }

  const saveGlobalCanonical = async () => {
    if (!tenantId || !reviewData) return;
    setCanonicalSaving(true); setCanonicalMessage(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const payload = {
        base_schema_ids: (reviewData?.input_snapshot?.schema_ids) || [],
        review_id: reviewData.review_id,
        user_edits: reviewData.suggestions || {},
      };
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/relationships/canonical`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Save failed');
      setCanonicalMessage(`Global canonical v${result.version} saved`);
      setSavedCanonical(result?.canonical_graph || null);
    } catch (e: any) {
      setCanonicalMessage(e.message || 'Failed to save');
    } finally {
      setCanonicalSaving(false);
    }
  };

  // Load latest saved canonical on mount/tenant change
  React.useEffect(() => {
    (async () => {
      if (!tenantId) return;
      try {
        setSavedCanonicalLoading(true);
        const token = window.localStorage.getItem('klaris_jwt');
        const resp = await fetch(`${API_URL}/tenants/${tenantId}/relationships/canonical/latest`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (!resp.ok) {
          // 404 means none saved yet – not an error
          setSavedCanonical(null);
          setSavedCanonicalVersion(null);
          return;
        }
        const result = await resp.json();
        setSavedCanonical(result?.canonical_graph || null);
        setSavedCanonicalVersion(result?.version ?? null);
      } catch {
        // Non-fatal in UI
      } finally {
        setSavedCanonicalLoading(false);
      }
    })();
  }, [tenantId]);

  function EntitiesTable({ entities }: { entities: any[] }) {
    return (
      <Table size="small" sx={{ mt: 1 }}>
        <TableHead>
          <TableRow>
            <TableCell>Name</TableCell>
            <TableCell>Tags</TableCell>
            <TableCell>Fields</TableCell>
            <TableCell>Sources</TableCell>
            <TableCell>Conf.</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {(entities || []).map((e, idx) => (
            <TableRow key={idx}>
              <TableCell>{e.name}</TableCell>
              <TableCell>{(e.tags || []).join(', ')}</TableCell>
              <TableCell>{(e.fields || []).map((f: any) => f.name).slice(0, 6).join(', ')}{(e.fields || []).length > 6 ? '…' : ''}</TableCell>
              <TableCell>{(e.source_mappings || []).length}</TableCell>
              <TableCell>{typeof e.confidence === 'number' ? e.confidence.toFixed(2) : ''}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }

  function RelationshipsTable({ rels }: { rels: any[] }) {
    return (
      <Table size="small" sx={{ mt: 2 }}>
        <TableHead>
          <TableRow>
            <TableCell>From</TableCell>
            <TableCell>To</TableCell>
            <TableCell>Type</TableCell>
            <TableCell>Description</TableCell>
            <TableCell>Conf.</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {(rels || []).map((r, idx) => (
            <TableRow key={idx}>
              <TableCell>{r.from_entity}{r.from_field ? `.${r.from_field}` : ''}</TableCell>
              <TableCell>{r.to_entity}{r.to_field ? `.${r.to_field}` : ''}</TableCell>
              <TableCell>{r.type}</TableCell>
              <TableCell>{r.description}</TableCell>
              <TableCell>{typeof r.confidence === 'number' ? r.confidence.toFixed(2) : ''}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>Data Relationships</Typography>
      {loading ? <CircularProgress /> : error ? <Alert severity="error">{error}</Alert> : (
        <>
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>Schema</AccordionSummary>
            <AccordionDetails>
              <List>
                {connectors.map((c) => (
                  <ListItem key={c.connector_id} secondaryAction={
                    <Button
                      size="small"
                      onClick={() => {
                        const entities = extractEntities(c.schema?.raw_schema);
                        setSchemaModal({ open: true, entities });
                      }}
                    >
                      View
                    </Button>
                  }>
                    <Checkbox
                      checked={selectedConnectorIds.includes(c.connector_id)}
                      onChange={(e) => {
                        setSelectedConnectorIds((ids) => e.target.checked ? [...ids, c.connector_id] : ids.filter(id => id !== c.connector_id));
                      }}
                    />
                    <ListItemText
                      primary={`${c.type} • ${c.connector_id}`}
                      secondary={(() => {
                        const count = extractEntities(c.schema?.raw_schema).length;
                        const ts = c.last_schema_fetch ? new Date(c.last_schema_fetch).toLocaleString() : 'Never';
                        return `${ts} • ${count} entities`;
                      })()}
                    />
                  </ListItem>
                ))}
              </List>
            </AccordionDetails>
          </Accordion>

          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>Enrich with AI</AccordionSummary>
            <AccordionDetails>
              <Stack direction="row" spacing={1} alignItems="center">
                <Button variant="contained" onClick={runEnrich} disabled={reviewLoading || selectedConnectorIds.length === 0}>
                  {reviewLoading ? 'Enriching…' : 'Start Enrich'}
                </Button>
              </Stack>
              {reviewError && <Alert severity="error" sx={{ mt: 1 }}>{reviewError}</Alert>}
            </AccordionDetails>
          </Accordion>

          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>Results</AccordionSummary>
            <AccordionDetails>
              {reviewLoading || savedCanonicalLoading ? (
                <Box display="flex" justifyContent="center" py={2}><CircularProgress /></Box>
              ) : savedCanonical ? (
                <>
                  <Typography variant="subtitle2">Unified Entities {savedCanonicalVersion ? `(v${savedCanonicalVersion})` : ''}</Typography>
                  <EntitiesTable entities={savedCanonical?.unified_entities || []} />
                  <Typography variant="subtitle2" sx={{ mt: 2 }}>Cross-Source Relationships</Typography>
                  <RelationshipsTable rels={savedCanonical?.cross_source_relationships || []} />
                  {canonicalMessage && (
                    <Alert severity={canonicalMessage.includes('saved') ? 'success' : 'error'} sx={{ mt: 1 }}>{canonicalMessage}</Alert>
                  )}
                </>
              ) : reviewData ? (
                <>
                  <Typography variant="subtitle2">Preview (AI Suggestions)</Typography>
                  <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                    <Box sx={{ p: 1.5 }}>
                      <JsonView src={reviewData?.suggestions || {}} theme="github" collapsed={1} enableClipboard />
                    </Box>
                  </Box>
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    <Button variant="outlined" onClick={saveGlobalCanonical} disabled={canonicalSaving}>
                      {canonicalSaving ? 'Saving…' : 'Publish Global Canonical'}
                    </Button>
                  </Stack>
                  {canonicalMessage && (
                    <Alert severity={canonicalMessage.includes('saved') ? 'success' : 'error'} sx={{ mt: 1 }}>{canonicalMessage}</Alert>
                  )}
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">Run Enrich to see results.</Typography>
              )}
            </AccordionDetails>
          </Accordion>

          <Dialog open={schemaModal.open} onClose={() => setSchemaModal({ open: false })} maxWidth="md" fullWidth>
            <DialogTitle>Schema Preview</DialogTitle>
            <DialogContent>
              <Box sx={{ p: 1.5 }}>
                <JsonView src={schemaModal.entities || []} theme="github" collapsed={1} enableClipboard />
              </Box>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setSchemaModal({ open: false })}>Close</Button>
            </DialogActions>
          </Dialog>
        </>
      )}
    </Box>
  );
}


