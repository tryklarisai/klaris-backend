import React from 'react';
import { Box, Typography, Accordion, AccordionSummary, AccordionDetails, Button, CircularProgress, Alert, Stack, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Table, TableHead, TableRow, TableCell, TableBody, Chip, IconButton, Select, MenuItem, Checkbox, Tooltip } from '@mui/material';
import Autocomplete from '@mui/material/Autocomplete';
import SaveIcon from '@mui/icons-material/Save';
import DeleteIcon from '@mui/icons-material/Delete';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { buildApiUrl } from '../config';

const API_URL = buildApiUrl('');

export default function BusinessContextPage() {
  const [tenantId, setTenantId] = React.useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [urlValue, setUrlValue] = React.useState('');
  const [glossFile, setGlossFile] = React.useState<File | null>(null);
  const [message, setMessage] = React.useState<string | null>(null);
  const [terms, setTerms] = React.useState<any[]>([]);
  const [termsLoading, setTermsLoading] = React.useState(false);
  const [termsError, setTermsError] = React.useState<string | null>(null);
  const [enrichLoading, setEnrichLoading] = React.useState(false);
  const [enrichError, setEnrichError] = React.useState<string | null>(null);
  const [suggestions, setSuggestions] = React.useState<any | null>(null);
  const [confThreshold, setConfThreshold] = React.useState<number>(0.6);
  const [draftContext, setDraftContext] = React.useState<any | null>(null);
  const [validateLoading, setValidateLoading] = React.useState(false);
  const [validateErrors, setValidateErrors] = React.useState<{ path: string; message: string }[] | null>(null);
  const [saveLoading, setSaveLoading] = React.useState(false);
  const [canonicalVersion, setCanonicalVersion] = React.useState<number | null>(null);
  const [canonicalMsg, setCanonicalMsg] = React.useState<string | null>(null);
  const [entities, setEntities] = React.useState<{ name: string; fields: string[] }[]>([]);
  const [savedContext, setSavedContext] = React.useState<any | null>(null);
  const [savedCtxLoading, setSavedCtxLoading] = React.useState(false);
  const [savedCtxError, setSavedCtxError] = React.useState<string | null>(null);

  React.useEffect(() => {
    const tStr = window.localStorage.getItem('klaris_tenant');
    if (tStr) setTenantId(JSON.parse(tStr).tenant_id);
  }, []);

  async function uploadUrl(type: 'url') {
    if (!tenantId) return;
    setUploading(true); setMessage(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const form = new FormData();
      form.append('type', type);
      form.append('url', urlValue);
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/business-context/sources`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Upload failed');
      setMessage('Source created');
      // no-op
    } catch (e: any) {
      setMessage(e.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  }

  async function uploadGlossary() {
    if (!tenantId || !glossFile) return;
    setUploading(true); setMessage(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const form = new FormData();
      form.append('file', glossFile);
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/business-context/glossary/import`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Import failed');
      setMessage(`Imported ${result?.imported_rows ?? 0} terms`);
      setGlossFile(null);
      // refresh glossary list
      await fetchTerms();
    } catch (e: any) {
      setMessage(e.message || 'Import failed');
    } finally {
      setUploading(false);
    }
  }

  async function fetchTerms() {
    if (!tenantId) return;
    setTermsLoading(true); setTermsError(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/business-context/terms?limit=500`, { headers: { Authorization: `Bearer ${token}` } });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Failed to load terms');
      setTerms(result || []);
    } catch (e: any) {
      setTermsError(e.message || 'Failed to load terms');
    } finally {
      setTermsLoading(false);
    }
  }

  React.useEffect(() => { fetchTerms(); /* eslint-disable-next-line */ }, [tenantId]);

  // Load canonical entities for mapping selectors
  React.useEffect(() => {
    (async () => {
      if (!tenantId) return;
      try {
        const token = window.localStorage.getItem('klaris_jwt');
        const resp = await fetch(`${API_URL}/tenants/${tenantId}/relationships/canonical/latest`, { headers: { Authorization: `Bearer ${token}` } });
        if (!resp.ok) return;
        const result = await resp.json();
        const cg = result?.canonical_graph || {};
        const ents = (cg.entities || []).map((e: any) => ({ name: e.name, fields: (e.fields || []).map((f: any) => f.name) }));
        setEntities(ents);
      } catch {}
    })();
  }, [tenantId]);

  async function loadSavedContext() {
    if (!tenantId) return;
    setSavedCtxLoading(true); setSavedCtxError(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/business-context/canonical/latest`, { headers: { Authorization: `Bearer ${token}` } });
      if (resp.status === 404) { setSavedContext(null); setSavedCtxLoading(false); return; }
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Failed to load context');
      setSavedContext(result?.canonical_context || null);
      setCanonicalVersion(result?.version ?? null);
    } catch (e: any) {
      setSavedCtxError(e.message || 'Failed to load context');
    } finally {
      setSavedCtxLoading(false);
    }
  }

  React.useEffect(() => { loadSavedContext(); /* eslint-disable-next-line */ }, [tenantId]);

  function setTermLocal(idx: number, patch: any) {
    setTerms((prev) => {
      const next = [...(prev || [])];
      next[idx] = { ...(next[idx] || {}), ...patch };
      return next;
    });
  }

  async function saveTerm(idx: number) {
    if (!tenantId) return;
    const t = terms[idx];
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/business-context/terms/${t.term_id}`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ term: t.term, description: t.description, synonyms: t.synonyms || [] })
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Save failed');
      setMessage('Term saved');
    } catch (e: any) {
      setMessage(e.message || 'Save failed');
    }
  }

  return (
    <Box>
      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Sources</AccordionSummary>
        <AccordionDetails>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <TextField size="small" placeholder="Add documentation URL" sx={{ width: 420 }} value={urlValue} onChange={(e) => setUrlValue(e.target.value)} />
            <Button variant="contained" disabled={uploading || !urlValue} onClick={() => uploadUrl('url')}>{uploading ? 'Uploading…' : 'Add URL'}</Button>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center">
            <input type="file" accept=".xlsx,.csv" onChange={(e) => setGlossFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)} />
            <Button variant="outlined" disabled={uploading || !glossFile} onClick={uploadGlossary}>{uploading ? 'Importing…' : 'Import Glossary'}</Button>
          </Stack>
          {message && <Alert severity={message.includes('failed') ? 'error' : 'success'} sx={{ mt: 1 }}>{message}</Alert>}
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Glossary</AccordionSummary>
        <AccordionDetails>
          {termsLoading ? (
            <CircularProgress size={22} />
          ) : termsError ? (
            <Alert severity="error">{termsError}</Alert>
          ) : (
            <Box>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Term</TableCell>
                    <TableCell>Description</TableCell>
                    <TableCell>Synonyms</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(terms || []).map((t, idx) => (
                    <TableRow key={t.term_id}>
                      <TableCell sx={{ width: 220 }}>
                        <TextField size="small" fullWidth value={t.term || ''} onChange={(e) => setTermLocal(idx, { term: e.target.value })} />
                      </TableCell>
                      <TableCell>
                        <TextField size="small" fullWidth value={t.description || ''} onChange={(e) => setTermLocal(idx, { description: e.target.value })} />
                      </TableCell>
                      <TableCell sx={{ minWidth: 260 }}>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" alignItems="center">
                          {(t.synonyms || []).map((s: string, i: number) => (
                            <Chip key={`${s}-${i}`} label={s} size="small" onDelete={() => setTermLocal(idx, { synonyms: (t.synonyms || []).filter((x: string, k: number) => k !== i) })} />
                          ))}
                          <TextField size="small" placeholder="Add synonym" onKeyDown={(ev: any) => { if (ev.key === 'Enter') { const v = (ev.target.value || '').trim(); if (v) setTermLocal(idx, { synonyms: [ ...(t.synonyms || []), v ] }); ev.target.value=''; } }} />
                        </Stack>
                      </TableCell>
                      <TableCell sx={{ width: 120 }}>
                        <IconButton size="small" onClick={() => saveTerm(idx)} title="Save"><SaveIcon fontSize="small" /></IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          )}
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Enrich with AI</AccordionSummary>
        <AccordionDetails>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <TextField size="small" label="Accept ≥ confidence" type="number" inputProps={{ min: 0, max: 1, step: 0.05 }} value={confThreshold} onChange={(e) => setConfThreshold(Number(e.target.value))} sx={{ width: 180 }} />
            <Button variant="contained" disabled={enrichLoading} onClick={async () => {
              if (!tenantId) return;
              setEnrichLoading(true); setEnrichError(null);
              try {
                const token = window.localStorage.getItem('klaris_jwt');
                const resp = await fetch(`${API_URL}/tenants/${tenantId}/business-context/reviews`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
                const result = await resp.json();
                if (!resp.ok) throw new Error(result?.detail || 'Review failed');
                const sugg = result?.suggestions || {};
                // Mark accepted mappings by threshold
                (sugg.terms || []).forEach((t: any) => {
                  (t.mappings = t.mappings || []).forEach((m: any) => { m.__accepted = (typeof m.confidence === 'number' ? m.confidence >= confThreshold : true); });
                });
                setSuggestions(sugg);
              } catch (e: any) {
                setEnrichError(e.message || 'Review failed');
              } finally {
                setEnrichLoading(false);
              }
            }}>{enrichLoading ? 'Generating…' : 'Generate Suggestions'}</Button>
            {enrichError && <Alert severity="error">{enrichError}</Alert>}
          </Stack>
          {suggestions && (
            <Box>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Term</TableCell>
                    <TableCell>Synonyms</TableCell>
                    <TableCell>Proposed mappings</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(suggestions.terms || []).map((t: any, i: number) => (
                    <TableRow key={i}>
                      <TableCell sx={{ width: 220 }}>{t.normalized_term || t.term}</TableCell>
                      <TableCell sx={{ minWidth: 220 }}>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap">{(t.synonyms || []).map((s: string, k: number) => <Chip key={`${s}-${k}`} label={s} size="small" />)}</Stack>
                      </TableCell>
                      <TableCell>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Accept</TableCell>
                              <TableCell>Entity</TableCell>
                              <TableCell>Field</TableCell>
                              <TableCell>Metric</TableCell>
                              <TableCell>Conf.</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {(t.mappings || []).map((m: any, j: number) => (
                              <TableRow key={j}>
                                <TableCell><Checkbox size="small" checked={!!m.__accepted} onChange={(e) => { const acc = e.target.checked; setSuggestions((prev: any) => { const next = JSON.parse(JSON.stringify(prev)); next.terms[i].mappings[j].__accepted = acc; return next; }); }} /></TableCell>
                                <TableCell>{m.entity_name}</TableCell>
                                <TableCell>{m.field_name}</TableCell>
                                <TableCell><Tooltip title={m.rationale || ''}><span>{(m.metric_def || '').slice(0, 24)}{(m.metric_def||'').length>24?'…':''}</span></Tooltip></TableCell>
                                <TableCell>{typeof m.confidence === 'number' ? m.confidence.toFixed(2) : ''}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Button variant="outlined" onClick={() => {
                  // Apply accepted suggestions to draft context
                  const draft = { terms: (suggestions.terms || []).map((t: any) => ({
                    term: t.term,
                    normalized_term: t.normalized_term || t.term,
                    description: t.description,
                    synonyms: t.synonyms || [],
                    mappings: (t.mappings || []).filter((m: any) => !!m.__accepted).map((m: any) => ({ entity_name: m.entity_name, field_name: m.field_name, metric_def: m.metric_def, rationale: m.rationale, confidence: m.confidence }))
                  })) };
                  setDraftContext(draft);
                }}>Apply to Draft</Button>
              </Stack>
            </Box>
          )}
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Editor</AccordionSummary>
        <AccordionDetails>
          {!draftContext ? (
            <Typography variant="body2" color="text.secondary">No draft yet. Generate suggestions or start from empty and add terms.</Typography>
          ) : (
            <Box>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Term</TableCell>
                    <TableCell>Description</TableCell>
                    <TableCell>Synonyms</TableCell>
                    <TableCell>Mappings</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(draftContext.terms || []).map((t: any, idx: number) => (
                    <TableRow key={idx}>
                      <TableCell sx={{ width: 200 }}>
                        <TextField size="small" value={t.normalized_term || ''} onChange={(e) => setDraftContext((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.terms[idx].normalized_term = e.target.value; return n; })} />
                      </TableCell>
                      <TableCell>
                        <TextField size="small" fullWidth value={t.description || ''} onChange={(e) => setDraftContext((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.terms[idx].description = e.target.value; return n; })} />
                      </TableCell>
                      <TableCell sx={{ minWidth: 220 }}>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap">
                          {(t.synonyms || []).map((s: string, i: number) => <Chip key={`${s}-${i}`} label={s} size="small" onDelete={() => setDraftContext((prev: any) => { const n = JSON.parse(JSON.stringify(prev)); n.terms[idx].synonyms.splice(i,1); return n; })} />)}
                          <TextField size="small" placeholder="Add synonym" onKeyDown={(ev: any) => { if (ev.key==='Enter'){ const v=(ev.target.value||'').trim(); if(v) setDraftContext((prev:any)=>{const n=JSON.parse(JSON.stringify(prev)); (n.terms[idx].synonyms = n.terms[idx].synonyms||[]).push(v); return n;}); ev.target.value=''; } }} />
                        </Stack>
                      </TableCell>
                      <TableCell sx={{ minWidth: 420 }}>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Entity</TableCell>
                              <TableCell>Field</TableCell>
                              <TableCell>Metric</TableCell>
                              <TableCell>Act</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {(t.mappings || []).map((m: any, j: number) => (
                              <TableRow key={j}>
                                <TableCell sx={{ width: 220 }}>
                                  <Autocomplete size="small" options={entities.map((e)=>e.name)} value={m.entity_name || ''} onChange={(_, val) => setDraftContext((prev:any)=>{const n=JSON.parse(JSON.stringify(prev)); n.terms[idx].mappings[j].entity_name = val || ''; n.terms[idx].mappings[j].field_name=''; return n;})} renderInput={(p)=><TextField {...p} placeholder="entity" />} />
                                </TableCell>
                                <TableCell sx={{ width: 220 }}>
                                  <Autocomplete size="small" options={(entities.find((e)=>e.name===m.entity_name)?.fields)||[]} value={m.field_name || ''} onChange={(_, val) => setDraftContext((prev:any)=>{const n=JSON.parse(JSON.stringify(prev)); n.terms[idx].mappings[j].field_name = val || ''; return n;})} renderInput={(p)=><TextField {...p} placeholder="field" />} />
                                </TableCell>
                                <TableCell>
                                  <TextField size="small" fullWidth placeholder="metric (optional)" value={m.metric_def || ''} onChange={(e)=> setDraftContext((prev:any)=>{const n=JSON.parse(JSON.stringify(prev)); n.terms[idx].mappings[j].metric_def=e.target.value; return n;})} />
                                </TableCell>
                                <TableCell sx={{ width: 80 }}>
                                  <IconButton size="small" onClick={()=> setDraftContext((prev:any)=>{const n=JSON.parse(JSON.stringify(prev)); n.terms[idx].mappings.splice(j,1); return n;})}><DeleteIcon fontSize="small" /></IconButton>
                                </TableCell>
                              </TableRow>
                            ))}
                            <TableRow>
                              <TableCell colSpan={4}><Button size="small" onClick={()=> setDraftContext((prev:any)=>{const n=JSON.parse(JSON.stringify(prev)); (n.terms[idx].mappings=n.terms[idx].mappings||[]).push({ entity_name:'', field_name:'', metric_def:'' }); return n;})}>Add Mapping</Button></TableCell>
                            </TableRow>
                          </TableBody>
                        </Table>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {validateErrors && validateErrors.length>0 && (
                <Alert severity="error" sx={{ mt: 1 }}>
                  <div>Validation errors:</div>
                  <ul style={{ margin:0, paddingLeft:16 }}>{validateErrors.map((e,i)=>(<li key={i}>{e.path}: {e.message}</li>))}</ul>
                </Alert>
              )}

              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Button variant="outlined" disabled={validateLoading} onClick={async()=>{
                  if(!tenantId||!draftContext) return;
                  setValidateLoading(true); setValidateErrors(null);
                  try{ const token=window.localStorage.getItem('klaris_jwt'); const resp=await fetch(`${API_URL}/tenants/${tenantId}/business-context/canonical/validate`, { method:'POST', headers:{ Authorization:`Bearer ${token}`, 'Content-Type':'application/json' }, body: JSON.stringify({ canonical_context: draftContext }) }); const result=await resp.json(); if(!resp.ok) throw new Error(result?.detail||'Validate failed'); setValidateErrors(result.ok?[]:(result.errors||[])); }catch(e:any){ setValidateErrors([{ path:'/', message:e.message||'Validate failed' }]); } finally{ setValidateLoading(false);}  }}> {validateLoading?'Validating…':'Validate'} </Button>
                <Button variant="contained" disabled={saveLoading} onClick={async()=>{
                  if(!tenantId||!draftContext) return;
                  setSaveLoading(true); setCanonicalMsg(null);
                  try{ const token=window.localStorage.getItem('klaris_jwt'); const payload={ user_edits: draftContext, expected_version: canonicalVersion??undefined }; const resp=await fetch(`${API_URL}/tenants/${tenantId}/business-context/canonical`, { method:'POST', headers:{ Authorization:`Bearer ${token}`, 'Content-Type':'application/json' }, body: JSON.stringify(payload) }); const result=await resp.json(); if(resp.status===409){ setCanonicalMsg('Version conflict. Reload latest.'); const latest=await fetch(`${API_URL}/tenants/${tenantId}/business-context/canonical/latest`, { headers:{ Authorization:`Bearer ${token}` } }); if(latest.ok){ const l=await latest.json(); setCanonicalVersion(l.version||null); setSavedContext(l.canonical_context || null);} return; } if(!resp.ok) throw new Error(result?.detail||'Save failed'); setCanonicalMsg(`Saved v${result.version}`); setCanonicalVersion(result.version||null); setSavedContext(result?.canonical_context || null); }catch(e:any){ setCanonicalMsg(e.message||'Save failed'); } finally{ setSaveLoading(false);}  }}>{saveLoading?'Saving…':'Save'}</Button>
              </Stack>
              {canonicalMsg && <Alert severity={canonicalMsg.startsWith('Saved')?'success':'warning'} sx={{ mt:1 }}>{canonicalMsg}</Alert>}
            </Box>
          )}
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Results</AccordionSummary>
        <AccordionDetails>
          {savedCtxLoading ? (
            <CircularProgress size={22} />
          ) : savedCtxError ? (
            <Alert severity="error">{savedCtxError}</Alert>
          ) : savedContext ? (
            <Box>
              <Typography variant="subtitle2">Latest Business Context {canonicalVersion ? `(v${canonicalVersion})` : ''}</Typography>
              <Table size="small" sx={{ mt: 1 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Term</TableCell>
                    <TableCell>Synonyms</TableCell>
                    <TableCell>Mappings</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(savedContext?.terms || []).map((t: any, i: number) => (
                    <TableRow key={i}>
                      <TableCell sx={{ width: 220 }}>{t.normalized_term || t.term}</TableCell>
                      <TableCell sx={{ minWidth: 220 }}>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap">{(t.synonyms || []).map((s: string, k: number) => <Chip key={`${s}-${k}`} label={s} size="small" />)}</Stack>
                      </TableCell>
                      <TableCell>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Entity</TableCell>
                              <TableCell>Field</TableCell>
                              <TableCell>Metric</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {(t.mappings || []).map((m: any, j: number) => (
                              <TableRow key={j}>
                                <TableCell>{m.entity_name}</TableCell>
                                <TableCell>{m.field_name}</TableCell>
                                <TableCell>{m.metric_def}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">No saved business context yet.</Typography>
          )}
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}


