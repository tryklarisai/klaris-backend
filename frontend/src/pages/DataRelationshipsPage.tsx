import React from 'react';
import { Box, Typography, Accordion, AccordionSummary, AccordionDetails, Button, CircularProgress, Alert, Stack, Checkbox, List, ListItem, ListItemText, Dialog, DialogTitle, DialogContent, DialogActions, Table, TableHead, TableRow, TableCell, TableBody, TextField, Select, MenuItem, IconButton, Chip, Paper, Switch, Tooltip } from '@mui/material';
import Autocomplete from '@mui/material/Autocomplete';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import JsonView from 'react18-json-view';
import 'react18-json-view/src/style.css';
import { buildApiUrl } from '../config';

const API_URL = buildApiUrl('');

export default function DataRelationshipsPage() {
  // Pilot-only: saved canonical is expected to have entities/relationships
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
  const [draftCanonical, setDraftCanonical] = React.useState<any | null>(null);
  const [validateLoading, setValidateLoading] = React.useState(false);
  const [validateErrors, setValidateErrors] = React.useState<{ path: string; message: string }[] | null>(null);
  const [savedBaseSchemaIds, setSavedBaseSchemaIds] = React.useState<string[] | null>(null);

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
        expected_version: savedCanonicalVersion ?? undefined,
      };
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/relationships/canonical`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      });
      const result = await resp.json();
      if (resp.status === 409) {
        const msg = typeof result?.detail === 'string' ? result.detail : (result?.detail?.message || 'Version conflict');
        setCanonicalMessage(`${msg}. Reloading latest...`);
        // Reload latest and show it
        try {
          const latestResp = await fetch(`${API_URL}/tenants/${tenantId}/relationships/canonical/latest`, { headers: { Authorization: `Bearer ${token}` } });
          if (latestResp.ok) {
            const latest = await latestResp.json();
            setSavedCanonical(latest?.canonical_graph || null);
            setSavedCanonicalVersion(latest?.version ?? null);
          }
        } catch {}
        return;
      }
      if (!resp.ok) throw new Error(result?.detail || 'Save failed');
      setCanonicalMessage(`Global canonical v${result.version} saved`);
      setSavedCanonical(result?.canonical_graph || null);
      setSavedCanonicalVersion(result?.version ?? null);
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
          setSavedBaseSchemaIds(null);
          return;
        }
        const result = await resp.json();
        setSavedCanonical(result?.canonical_graph || null);
        setSavedCanonicalVersion(result?.version ?? null);
        setSavedBaseSchemaIds(result?.base_schema_ids || []);
      } catch {
        // Non-fatal in UI
      } finally {
        setSavedCanonicalLoading(false);
      }
    })();
  }, [tenantId]);

  // Begin edit flow: copy saved to draft
  const beginEdit = () => {
    if (!savedCanonical) return;
    setDraftCanonical(JSON.parse(JSON.stringify(savedCanonical)));
    setValidateErrors(null);
  };

  const discardEdit = () => {
    setDraftCanonical(null);
    setValidateErrors(null);
  };

  const doValidate = async () => {
    if (!tenantId || !draftCanonical) return;
    setValidateLoading(true); setValidateErrors(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/relationships/canonical/validate`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ canonical_graph: draftCanonical })
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Validation failed');
      if (result?.ok) setValidateErrors([]);
      else setValidateErrors(result?.errors || []);
    } catch (e: any) {
      setValidateErrors([{ path: '/', message: e.message || 'Validation failed' }]);
    } finally {
      setValidateLoading(false);
    }
  };

  function EntitiesTable({ entities }: { entities: any[] }) {
    return (
      <Table size="small" sx={{ mt: 1 }}>
        <TableHead>
          <TableRow>
            <TableCell>Name</TableCell>
            <TableCell>Tags</TableCell>
            <TableCell>Fields</TableCell>
            <TableCell>Mappings</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {(entities || []).map((e, idx) => (
            <TableRow key={idx}>
              <TableCell>{e.name}</TableCell>
              <TableCell>{(e.tags || []).join(', ')}</TableCell>
              <TableCell>{(e.fields || []).map((f: any) => f.name).slice(0, 6).join(', ')}{(e.fields || []).length > 6 ? '…' : ''}</TableCell>
              <TableCell>{(e.fields || []).reduce((acc: number, f: any) => acc + ((f.mappings || []).length || 0), 0)}</TableCell>
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
            <TableCell>Join On</TableCell>
            <TableCell>Confidence</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {(rels || []).map((r, idx) => (
            <TableRow key={idx}>
              <TableCell>{r.from_entity}</TableCell>
              <TableCell>{r.to_entity}</TableCell>
              <TableCell>{r.type}</TableCell>
              <TableCell>{Array.isArray(r.join_on) ? r.join_on.map((p: any) => `${p.from_field} = ${r.to_entity}.${p.to_field}`).join(', ') : ''}</TableCell>
              <TableCell>{typeof r.confidence === 'number' ? r.confidence.toFixed(2) : ''}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }

  // ---------- Editable components ----------
  function EditableEntitiesTable({ entities }: { entities: any[] }) {
    const onEntityChange = (i: number, patch: any) => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || {}));
        next.entities[i] = { ...(next.entities[i] || {}), ...patch };
        return next;
      });
    };
    const onFieldChange = (i: number, j: number, patch: any) => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || {}));
        next.entities[i].fields[j] = { ...(next.entities[i].fields[j] || {}), ...patch };
        return next;
      });
    };
    const addEntity = () => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || { entities: [] }));
        (next.entities = next.entities || []).push({ name: 'New Entity', description: '', fields: [] });
        return next;
      });
    };
    const removeEntity = (i: number) => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || {}));
        next.entities.splice(i, 1);
        return next;
      });
    };
    const addField = (i: number) => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || {}));
        (next.entities[i].fields = next.entities[i].fields || []).push({ name: 'new_field', description: '', semantic_type: '', pii_sensitivity: 'none', nullable: false, data_type: '' });
        return next;
      });
    };
    const removeField = (i: number, j: number) => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || {}));
        next.entities[i].fields.splice(j, 1);
        return next;
      });
    };
    const addTag = (i: number, tag: string) => {
      const t = (tag || '').trim(); if (!t) return;
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || {}));
        const tags = (next.entities[i].tags = next.entities[i].tags || []);
        if (!tags.includes(t)) tags.push(t);
        return next;
      });
    };
    const removeTag = (i: number, tag: string) => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || {}));
        next.entities[i].tags = (next.entities[i].tags || []).filter((x: string) => x !== tag);
        return next;
      });
    };

    const headerCellSx = { position: 'sticky', top: 0, backgroundColor: 'background.paper', zIndex: 1, fontSize: 12 } as const;
    const colSx = {
      name: { width: 160 },
      desc: { width: 260 },
      semantic: { width: 140 },
      pii: { width: 110 },
      nullable: { width: 80 },
      dtype: { width: 140 },
      act: { width: 64, textAlign: 'right' },
    } as const;

    return (
      <Box>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <Button startIcon={<AddIcon />} onClick={addEntity}>Add Entity</Button>
        </Stack>
        <Stack direction="column" spacing={1}>
          {(entities || []).map((e, i) => (
            <Paper key={i} variant="outlined" sx={{ p: 1.25 }}>
              <Box sx={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 2fr', gap: 1 }}>
                <Box>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                    <TextField size="small" placeholder="Name" value={e.name || ''} onChange={(ev) => onEntityChange(i, { name: ev.target.value })} sx={{ width: 220 }} />
                    <IconButton onClick={() => removeEntity(i)} aria-label="remove entity"><DeleteIcon fontSize="small" /></IconButton>
                  </Stack>
                  <TextField size="small" placeholder="Description" value={e.description || ''} onChange={(ev) => onEntityChange(i, { description: ev.target.value })} fullWidth sx={{ mb: 0.5 }} />
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" alignItems="center">
                    {(e.tags || []).map((t: string, idx: number) => (
                      <Chip key={idx} label={t} size="small" onDelete={() => removeTag(i, t)} sx={{ mr: 0.5, mb: 0.5 }} />
                    ))}
                    <TextField size="small" placeholder="Add tag" onKeyDown={(ev: any) => { if (ev.key === 'Enter') { addTag(i, ev.target.value); ev.target.value=''; } }} sx={{ width: 180 }} />
                  </Stack>
                </Box>
                <Box>
                  <Box sx={{ maxHeight: 360, overflow: 'auto', border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ ...headerCellSx, ...colSx.name }}>Name</TableCell>
                          <TableCell sx={{ ...headerCellSx, ...colSx.desc }}>Description</TableCell>
                          <TableCell sx={{ ...headerCellSx, ...colSx.semantic }}>Semantic</TableCell>
                          <TableCell sx={{ ...headerCellSx, ...colSx.pii }}>PII</TableCell>
                          <TableCell sx={{ ...headerCellSx, ...colSx.nullable }}>Null</TableCell>
                          <TableCell sx={{ ...headerCellSx, ...colSx.dtype }}>Type</TableCell>
                          <TableCell sx={{ ...headerCellSx, width: 110 }}>Confidence</TableCell>
                          <TableCell sx={{ ...headerCellSx, ...colSx.act }}>Act</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(e.fields || []).map((f: any, j: number) => (
                          <TableRow key={j}>
                            <TableCell sx={colSx.name}>
                              <Tooltip title={f.name || ''}><TextField size="small" placeholder="name" value={f.name || ''} onChange={(ev) => onFieldChange(i, j, { name: ev.target.value })} /></Tooltip>
                            </TableCell>
                            <TableCell sx={colSx.desc}>
                              <Tooltip title={f.description || ''}><TextField size="small" placeholder="description" value={f.description || ''} onChange={(ev) => onFieldChange(i, j, { description: ev.target.value })} fullWidth /></Tooltip>
                            </TableCell>
                            <TableCell sx={colSx.semantic}><TextField size="small" placeholder="semantic" value={f.semantic_type || ''} onChange={(ev) => onFieldChange(i, j, { semantic_type: ev.target.value })} /></TableCell>
                            <TableCell sx={colSx.pii}>
                              <Select size="small" value={(f.pii_sensitivity || 'none')} onChange={(ev) => onFieldChange(i, j, { pii_sensitivity: ev.target.value })} fullWidth>
                                {['none','low','medium','high'].map(opt => <MenuItem key={opt} value={opt}>{opt}</MenuItem>)}
                              </Select>
                            </TableCell>
                            <TableCell sx={colSx.nullable}><Switch size="small" checked={!!f.nullable} onChange={(ev) => onFieldChange(i, j, { nullable: ev.target.checked })} /></TableCell>
                            <TableCell sx={colSx.dtype}><TextField size="small" placeholder="type" value={f.data_type || ''} onChange={(ev) => onFieldChange(i, j, { data_type: ev.target.value })} /></TableCell>
                            <TableCell sx={{ width: 110 }}>
                              <TextField size="small" type="number" inputProps={{ readOnly: true }} value={typeof f.confidence === 'number' ? f.confidence.toFixed(2) : ''} />
                            </TableCell>
                            <TableCell sx={colSx.act}><IconButton size="small" onClick={() => removeField(i, j)} aria-label="remove field"><DeleteIcon fontSize="small" /></IconButton></TableCell>
                          </TableRow>
                        ))}
                        <TableRow>
                          <TableCell colSpan={8}><Button size="small" startIcon={<AddIcon />} onClick={() => addField(i)}>Add Field</Button></TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </Box>
                </Box>
              </Box>
            </Paper>
          ))}
        </Stack>
      </Box>
    );
  }

  function EditableRelationshipsTable({ rels }: { rels: any[] }) {
    const entityNames = (draftCanonical?.entities || []).map((e: any) => e.name as string);
    const fieldsByEntity: Record<string, string[]> = Object.fromEntries((draftCanonical?.entities || []).map((e: any) => [e.name, (e.fields || []).map((f: any) => f.name)]));
    const onRelChange = (k: number, patch: any) => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || {}));
        next.relationships[k] = { ...(next.relationships[k] || {}), ...patch };
        return next;
      });
    };
    const addRel = () => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || { relationships: [] }));
        (next.relationships = next.relationships || []).push({ from_entity: '', to_entity: '', type: 'unknown', join_on: [], confidence: 0 });
        return next;
      });
    };
    const removeRel = (k: number) => {
      setDraftCanonical((prev: any) => {
        const next = JSON.parse(JSON.stringify(prev || {}));
        next.relationships.splice(k, 1);
        return next;
      });
    };
    return (
      <Box>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>From Entity</TableCell>
              <TableCell>From Field</TableCell>
              <TableCell>To Entity</TableCell>
              <TableCell>To Field</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Confidence</TableCell>
              <TableCell>Act</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(rels || []).map((r: any, k: number) => (
              <TableRow key={k}>
                <TableCell>
                  <Autocomplete size="small" sx={{ minWidth: 180 }} options={entityNames}
                    value={r.from_entity || ''}
                    onChange={(_, val) => onRelChange(k, { from_entity: val || '', from_field: '' })}
                    renderInput={(params) => <TextField {...params} placeholder="entity" />} />
                </TableCell>
                <TableCell>
                  <Autocomplete size="small" sx={{ minWidth: 240 }} multiple options={((fieldsByEntity[r.from_entity] || []) as string[])}
                    value={Array.isArray(r.join_on) ? r.join_on.map((p: any) => p.from_field) : []}
                    onChange={(_, vals) => {
                      const pairs = (vals as string[]).map((ff: string, idx: number) => ({ from_field: ff, to_field: (r.join_on?.[idx]?.to_field) || '' }));
                      onRelChange(k, { join_on: pairs });
                    }}
                    renderInput={(params) => <TextField {...params} placeholder="from fields" />} />
                </TableCell>
                <TableCell>
                  <Autocomplete size="small" sx={{ minWidth: 180 }} options={entityNames}
                    value={r.to_entity || ''}
                    onChange={(_, val) => onRelChange(k, { to_entity: val || '', join_on: [] })}
                    renderInput={(params) => <TextField {...params} placeholder="entity" />} />
                </TableCell>
                <TableCell>
                  <Autocomplete size="small" sx={{ minWidth: 240 }} multiple options={((fieldsByEntity[r.to_entity] || []) as string[])}
                    value={Array.isArray(r.join_on) ? r.join_on.map((p: any) => p.to_field) : []}
                    onChange={(_, vals) => {
                      const pairs = (vals as string[]).map((tf: string, idx: number) => ({ from_field: (r.join_on?.[idx]?.from_field) || '', to_field: tf }));
                      onRelChange(k, { join_on: pairs });
                    }}
                    renderInput={(params) => <TextField {...params} placeholder="to fields" />} />
                </TableCell>
                <TableCell>
                  <Select size="small" value={r.type || 'unknown'} onChange={(ev) => onRelChange(k, { type: ev.target.value })}>
                    {['one_to_one','one_to_many','many_to_one','many_to_many','unknown'].map(t => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                  </Select>
                </TableCell>
                <TableCell><TextField size="small" type="number" inputProps={{ readOnly: true }} sx={{ width: 120 }} value={typeof r.confidence === 'number' ? r.confidence.toFixed(2) : ''} /></TableCell>
                <TableCell><IconButton size="small" onClick={() => removeRel(k)}><DeleteIcon fontSize="small" /></IconButton></TableCell>
              </TableRow>
            ))}
            <TableRow>
              <TableCell colSpan={7}>
                <Button size="small" startIcon={<AddIcon />} onClick={addRel}>Add Relationship</Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </Box>
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
              ) : savedCanonical ? (
                <>
                  <Typography variant="subtitle2">Entities {savedCanonicalVersion ? `(v${savedCanonicalVersion})` : ''}</Typography>
                  <EntitiesTable entities={savedCanonical?.entities || []} />
                  <Typography variant="subtitle2" sx={{ mt: 2 }}>Relationships</Typography>
                  <RelationshipsTable rels={savedCanonical?.relationships || []} />
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    <Button variant="contained" onClick={beginEdit}>Edit Canonical</Button>
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

          {draftCanonical && (
            <Accordion defaultExpanded>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>Editor</AccordionSummary>
              <AccordionDetails>
                <Typography variant="subtitle2">Draft Entities</Typography>
                <EditableEntitiesTable entities={draftCanonical?.entities || []} />
                <Typography variant="subtitle2" sx={{ mt: 2 }}>Draft Relationships</Typography>
                <EditableRelationshipsTable rels={draftCanonical?.relationships || []} />
                {validateErrors && validateErrors.length > 0 && (
                  <Alert severity="error" sx={{ mt: 1 }}>
                    <div>Validation errors:</div>
                    <ul style={{ margin: 0, paddingLeft: 16 }}>
                      {validateErrors.map((e, i) => <li key={i}>{e.path}: {e.message}</li>)}
                    </ul>
                  </Alert>
                )}
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <Button variant="outlined" onClick={doValidate} disabled={validateLoading}>{validateLoading ? 'Validating…' : 'Validate'}</Button>
                  <Button
                    variant="contained"
                    onClick={async () => {
                      if (!tenantId || !draftCanonical) return;
                      setCanonicalSaving(true); setCanonicalMessage(null);
                      try {
                        const token = window.localStorage.getItem('klaris_jwt');
                        const payload = {
                          base_schema_ids: savedCanonicalVersion ? (reviewData?.input_snapshot?.schema_ids || []) : (reviewData?.input_snapshot?.schema_ids || []),
                          user_edits: draftCanonical,
                          expected_version: savedCanonicalVersion ?? undefined,
                        };
                        const resp = await fetch(`${API_URL}/tenants/${tenantId}/relationships/canonical`, {
                          method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
                        });
                        const result = await resp.json();
                        if (resp.status === 409) {
                          setCanonicalMessage('Version conflict. Reloading latest...');
                          const latestResp = await fetch(`${API_URL}/tenants/${tenantId}/relationships/canonical/latest`, { headers: { Authorization: `Bearer ${token}` } });
                          if (latestResp.ok) {
                            const latest = await latestResp.json();
                            setSavedCanonical(latest?.canonical_graph || null);
                            setSavedCanonicalVersion(latest?.version ?? null);
                            setDraftCanonical(null);
                          }
                          return;
                        }
                        if (!resp.ok) throw new Error(result?.detail || 'Save failed');
                        setCanonicalMessage(`Global canonical v${result.version} saved`);
                        setSavedCanonical(result?.canonical_graph || null);
                        setSavedCanonicalVersion(result?.version ?? null);
                        setDraftCanonical(null);
                      } catch (e: any) {
                        setCanonicalMessage(e.message || 'Failed to save');
                      } finally {
                        setCanonicalSaving(false);
                      }
                    }}
                    disabled={canonicalSaving}
                  >
                    {canonicalSaving ? 'Saving…' : 'Save'}
                  </Button>
                  <Button variant="text" color="inherit" onClick={discardEdit}>Discard</Button>
                </Stack>
              </AccordionDetails>
            </Accordion>
          )}

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


