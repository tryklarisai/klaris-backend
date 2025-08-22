import React from "react";
import {
  Box,
  Typography,
  Paper,
  Button,
  TextField,
  Stack,
  Select,
  MenuItem,
  InputLabel,
  FormControl,
  Divider,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from "@mui/material";
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { buildApiUrl } from "../config";

type DocumentUploadResponse = {
  document_id: string;
  chunks: number;
  status: string;
  error?: string;
};

type TermMapping = {
  mapping_id: string;
  target_kind: string;
  entity_name?: string | null;
  field_name?: string | null;
  expression?: any;
  filter?: any;
  rationale?: string | null;
  confidence?: number | null;
};

type Term = {
  term_id: string;
  term: string;
  normalized_term: string;
  description?: string | null;
  aliases: string[];
  mappings: TermMapping[];
  score?: number | null;
};

type EvidenceSnippet = {
  chunk_id: string;
  text: string;
  score: number;
  document_id: string;
  document_uri?: string | null;
  metadata?: any;
};

type GroundResponse = {
  terms: Term[];
  evidence: EvidenceSnippet[];
};

function useAuthHeaders() {
  return React.useMemo(() => {
    const token = window.localStorage.getItem("klaris_jwt");
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
  }, []);
}

export default function BclPage() {
  const headers = useAuthHeaders();

  // Upload
  const [uploading, setUploading] = React.useState(false);
  const [uploadResult, setUploadResult] = React.useState<DocumentUploadResponse | null>(null);
  const uploadInputRef = React.useRef<HTMLInputElement | null>(null);

  async function handleUpload() {
    const fileInput = uploadInputRef.current;
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) return;
    const file = fileInput.files[0];
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    setUploadResult(null);
    try {
      const resp = await fetch(buildApiUrl("/api/v1/bcl/documents/upload"), {
        method: "POST",
        headers,
        body: fd,
      } as RequestInit);
      const data = await resp.json();
      setUploadResult(data);
    } catch (e) {
      setUploadResult({ document_id: "", chunks: 0, status: "error", error: String(e) });
    } finally {
      setUploading(false);
    }
  }

  // Glossary import
  const glossaryInputRef = React.useRef<HTMLInputElement | null>(null);
  const [glossaryLoading, setGlossaryLoading] = React.useState(false);
  const [glossaryResult, setGlossaryResult] = React.useState<any | null>(null);

  async function handleImportGlossary() {
    const input = glossaryInputRef.current;
    if (!input || !input.files || input.files.length === 0) return;
    const file = input.files[0];
    const fd = new FormData();
    fd.append("file", file);
    setGlossaryLoading(true);
    setGlossaryResult(null);
    try {
      const resp = await fetch(buildApiUrl("/api/v1/bcl/glossary/import"), {
        method: "POST",
        headers,
        body: fd,
      } as RequestInit);
      const data = await resp.json();
      setGlossaryResult(data);
    } catch (e) {
      setGlossaryResult({ error: String(e) });
    } finally {
      setGlossaryLoading(false);
    }
  }

  // Ground
  const [query, setQuery] = React.useState("revenue");
  const [grounding, setGrounding] = React.useState(false);
  const [groundData, setGroundData] = React.useState<GroundResponse | null>(null);

  async function handleGround() {
    setGrounding(true);
    setGroundData(null);
    try {
      const resp = await fetch(buildApiUrl("/api/v1/bcl/ground"), {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k_terms: 5, top_k_evidence: 5 }),
      } as RequestInit);
      const data = await resp.json();
      setGroundData(data);
    } finally {
      setGrounding(false);
    }
  }

  // Mapping creation state per term
  const [newMapping, setNewMapping] = React.useState<Record<string, Partial<TermMapping>>>({});

  function updateNewMapping(termId: string, patch: Partial<TermMapping>) {
    setNewMapping((s) => ({ ...s, [termId]: { ...s[termId], ...patch } }));
  }

  async function createMapping(termId: string) {
    const payload = newMapping[termId];
    if (!payload || !payload.target_kind) return;
    const resp = await fetch(buildApiUrl(`/api/v1/bcl/terms/${encodeURIComponent(termId)}/mappings`), {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    } as RequestInit);
    const data = await resp.json();
    // Refresh ground output to reflect new mapping
    await handleGround();
    // Clear form
    setNewMapping((s) => ({ ...s, [termId]: {} }));
    return data;
  }

  async function deleteMapping(mappingId: string) {
    await fetch(buildApiUrl(`/api/v1/bcl/mappings/${encodeURIComponent(mappingId)}`), {
      method: "DELETE",
      headers,
    } as RequestInit);
    await handleGround();
  }

  return (
    <Box sx={{ mt: 7 }}>
      <Typography variant="h4" sx={{ mb: 1 }}>Business Context</Typography>

      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Upload Documents</AccordionSummary>
        <AccordionDetails>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
            <input ref={uploadInputRef} type="file" accept=".csv,.xlsx,.xls,.txt,.pdf" />
            <Button variant="contained" onClick={handleUpload} disabled={uploading}>Upload</Button>
          </Stack>
          {!!uploadResult && (
            <Typography sx={{ mt: 2 }} color={uploadResult.error ? "error" : "text.primary"}>
              Result: {uploadResult.status} — chunks: {uploadResult.chunks}{uploadResult.error ? ` — ${uploadResult.error}` : ""}
            </Typography>
          )}
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Import Business Glossary</AccordionSummary>
        <AccordionDetails>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
            <input ref={glossaryInputRef} type="file" accept=".csv,.xlsx,.xls" />
            <Button variant="contained" onClick={handleImportGlossary} disabled={glossaryLoading}>Import</Button>
          </Stack>
          {!!glossaryResult && (
            <Typography sx={{ mt: 2 }}>
              {glossaryResult.error ? (
                <span style={{ color: "#d32f2f" }}>Error: {glossaryResult.error}</span>
              ) : (
                `Terms upserted: ${glossaryResult.terms_upserted}, Aliases: ${glossaryResult.aliases_created}, Rows: ${glossaryResult.rows_processed}`
              )}
            </Typography>
          )}
        </AccordionDetails>
      </Accordion>

      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Ground</AccordionSummary>
        <AccordionDetails>
          <Stack spacing={3}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" sx={{ mb: 2 }}>Ground a Query</Typography>
              <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
                <TextField fullWidth label="Query" value={query} onChange={(e) => setQuery(e.target.value)} />
                <Button variant="contained" onClick={handleGround} disabled={grounding || !query}>Search</Button>
              </Stack>
            </Paper>

            {groundData && (
              <Stack spacing={3}>
                <Paper sx={{ p: 3 }}>
                  <Typography variant="subtitle1" sx={{ mb: 1 }}>Terms</Typography>
                  <Stack spacing={2}>
                    {groundData.terms.length === 0 && (
                      <Typography color="text.secondary">No terms found.</Typography>
                    )}
                    {groundData.terms.map((t) => (
                      <Paper key={t.term_id} sx={{ p: 2 }} variant="outlined">
                        <Stack spacing={1}>
                          <Stack direction="row" spacing={1} alignItems="center">
                            <Typography variant="subtitle1">{t.term}</Typography>
                            {typeof t.score === "number" && (
                              <Chip size="small" label={`score ${(t.score as number).toFixed(2)}`} />
                            )}
                          </Stack>
                          {!!t.description && <Typography color="text.secondary">{t.description}</Typography>}
                          {t.aliases.length > 0 && (
                            <Typography variant="body2">Aliases: {t.aliases.join(", ")}</Typography>
                          )}
                          {t.mappings.length > 0 ? (
                            <Stack spacing={0.5}>
                              <Typography variant="body2" sx={{ mt: 1 }}>Mappings:</Typography>
                              {t.mappings.map((m) => (
                                <Stack key={m.mapping_id} direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ md: "center" }}>
                                  <Typography variant="body2">
                                    {m.target_kind} {m.entity_name || ""}{m.field_name ? "." + m.field_name : ""}
                                    {m.rationale ? ` — ${m.rationale}` : ""}
                                  </Typography>
                                  <Button size="small" color="error" onClick={() => deleteMapping(m.mapping_id)}>Delete</Button>
                                </Stack>
                              ))}
                            </Stack>
                          ) : (
                            <Typography variant="body2" color="text.secondary">No mappings yet.</Typography>
                          )}

                          <Divider sx={{ my: 1 }} />
                          <Typography variant="body2">Create mapping</Typography>
                          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                            <FormControl size="small" sx={{ minWidth: 160 }}>
                              <InputLabel id={`target-kind-${t.term_id}`}>Target Kind</InputLabel>
                              <Select
                                labelId={`target-kind-${t.term_id}`}
                                label="Target Kind"
                                value={newMapping[t.term_id]?.target_kind || ""}
                                onChange={(e) => updateNewMapping(t.term_id, { target_kind: String(e.target.value) })}
                              >
                                <MenuItem value="table">table</MenuItem>
                                <MenuItem value="column">column</MenuItem>
                                <MenuItem value="expression">expression</MenuItem>
                                <MenuItem value="filter">filter</MenuItem>
                              </Select>
                            </FormControl>
                            <TextField
                              size="small"
                              label="Entity name"
                              value={newMapping[t.term_id]?.entity_name || ""}
                              onChange={(e) => updateNewMapping(t.term_id, { entity_name: e.target.value })}
                            />
                            <TextField
                              size="small"
                              label="Field name"
                              value={newMapping[t.term_id]?.field_name || ""}
                              onChange={(e) => updateNewMapping(t.term_id, { field_name: e.target.value })}
                            />
                          </Stack>
                          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                            <TextField
                              size="small"
                              label="Expression (JSON)"
                              fullWidth
                              value={newMapping[t.term_id]?.expression ? JSON.stringify(newMapping[t.term_id]?.expression) : ""}
                              onChange={(e) => {
                                try { updateNewMapping(t.term_id, { expression: e.target.value ? JSON.parse(e.target.value) : undefined }); } catch {}
                              }}
                            />
                            <TextField
                              size="small"
                              label="Filter (JSON)"
                              fullWidth
                              value={newMapping[t.term_id]?.filter ? JSON.stringify(newMapping[t.term_id]?.filter) : ""}
                              onChange={(e) => {
                                try { updateNewMapping(t.term_id, { filter: e.target.value ? JSON.parse(e.target.value) : undefined }); } catch {}
                              }}
                            />
                          </Stack>
                          <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ md: "center" }}>
                            <TextField
                              size="small"
                              label="Rationale"
                              fullWidth
                              value={newMapping[t.term_id]?.rationale || ""}
                              onChange={(e) => updateNewMapping(t.term_id, { rationale: e.target.value })}
                            />
                            <TextField
                              size="small"
                              label="Confidence"
                              type="number"
                              value={newMapping[t.term_id]?.confidence ?? ""}
                              onChange={(e) => updateNewMapping(t.term_id, { confidence: e.target.value ? Number(e.target.value) : undefined })}
                            />
                            <Button variant="outlined" onClick={() => createMapping(t.term_id)}>Save</Button>
                          </Stack>
                        </Stack>
                      </Paper>
                    ))}
                  </Stack>
                </Paper>

                <Paper sx={{ p: 3 }}>
                  <Typography variant="subtitle1" sx={{ mb: 1 }}>Evidence</Typography>
                  <Stack spacing={2}>
                    {groundData.evidence.length === 0 && (
                      <Typography color="text.secondary">No evidence found.</Typography>
                    )}
                    {groundData.evidence.map((e) => (
                      <Paper key={e.chunk_id} sx={{ p: 2 }} variant="outlined">
                        <Typography
                          variant="body2"
                          sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}
                        >
                          {e.text}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          score {(e.score).toFixed(2)} — {e.document_uri || e.document_id}
                        </Typography>
                      </Paper>
                    ))}
                  </Stack>
                </Paper>
              </Stack>
            )}
          </Stack>
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Proposals</AccordionSummary>
        <AccordionDetails>
          <ProposalsSection />
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}

function ProposalsSection() {
  const headers = useAuthHeaders();
  const [loading, setLoading] = React.useState(false);
  const [proposals, setProposals] = React.useState<any[]>([]);

  const fetchProposals = React.useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch(buildApiUrl('/api/v1/bcl/proposals'), { headers } as RequestInit);
      const data = await resp.json();
      setProposals(Array.isArray(data?.proposals) ? data.proposals : []);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  React.useEffect(() => { fetchProposals(); }, [fetchProposals]);

  async function proposeAll() {
    setLoading(true);
    try {
      await fetch(buildApiUrl('/api/v1/bcl/propose-mappings'), { method: 'POST', headers } as RequestInit);
      await fetchProposals();
    } finally {
      setLoading(false);
    }
  }

  async function acceptProposal(id: string) {
    setLoading(true);
    try {
      await fetch(buildApiUrl(`/api/v1/bcl/proposals/${encodeURIComponent(id)}/accept`), { method: 'POST', headers } as RequestInit);
      await fetchProposals();
    } finally {
      setLoading(false);
    }
  }

  async function rejectProposal(id: string) {
    setLoading(true);
    try {
      await fetch(buildApiUrl(`/api/v1/bcl/proposals/${encodeURIComponent(id)}/reject`), { method: 'POST', headers } as RequestInit);
      await fetchProposals();
    } finally {
      setLoading(false);
    }
  }

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
        <Button variant="contained" onClick={proposeAll} disabled={loading}>Propose mappings for all terms</Button>
        <Button variant="outlined" onClick={fetchProposals} disabled={loading}>Refresh</Button>
      </Stack>
      {loading && <Typography color="text.secondary">Working…</Typography>}
      {proposals.length === 0 ? (
        <Typography color="text.secondary">No proposals yet.</Typography>
      ) : (
        proposals.map((p) => (
          <Paper key={p.proposal_id} sx={{ p: 2 }} variant="outlined">
            <Stack spacing={1}>
              <Typography variant="subtitle1">{p.term}</Typography>
              <Typography variant="body2" color="text.secondary">
                {p.target_kind} {p.entity_name || ''}{p.field_name ? '.' + p.field_name : ''}
              </Typography>
              {p.rationale && <Typography variant="body2">{p.rationale}</Typography>}
              <Stack direction="row" spacing={1}>
                <Button size="small" variant="contained" onClick={() => acceptProposal(p.proposal_id)}>Accept</Button>
                <Button size="small" color="error" variant="outlined" onClick={() => rejectProposal(p.proposal_id)}>Reject</Button>
              </Stack>
            </Stack>
          </Paper>
        ))
      )}
    </Stack>
  );
}



