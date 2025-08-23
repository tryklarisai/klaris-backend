import React from "react";
import {
  Box,
  Typography,
  Paper,
  Button,
  TextField,
  Stack,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from "@mui/material";
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { buildApiUrl } from "../config";
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';

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

  return (
    <Box sx={{ mt: 7 }}>
      <Typography variant="h4" sx={{ mb: 1 }}>Glossary</Typography>

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
                `Terms upserted: ${glossaryResult.terms_upserted}, Rows: ${glossaryResult.rows_processed}`
              )}
            </Typography>
          )}
        </AccordionDetails>
      </Accordion>

      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Search Glossary</AccordionSummary>
        <AccordionDetails>
          <GlossarySearch />
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}

function GlossarySearch() {
  const headers = useAuthHeaders();
  const [q, setQ] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [items, setItems] = React.useState<any[]>([]);
  const [topK, setTopK] = React.useState(20);
  const [editing, setEditing] = React.useState<Record<string, { term: string; description: string }>>({});

  const doSearch = React.useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ q, top_k: String(topK) });
      const resp = await fetch(buildApiUrl(`/api/v1/bcl/terms?${params.toString()}`), { headers } as RequestInit);
      const data = await resp.json();
      setItems(Array.isArray(data?.terms) ? data.terms : []);
    } finally {
      setLoading(false);
    }
  }, [q, topK, headers]);

  React.useEffect(() => { doSearch(); }, []);

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
        <TextField size="small" label="Search" value={q} onChange={(e) => setQ(e.target.value)} sx={{ minWidth: 320 }} />
        <TextField size="small" label="Top K" type="number" value={topK} onChange={(e) => setTopK(Math.max(1, Number(e.target.value || 20)))} sx={{ width: 120 }} />
        <Button variant="contained" onClick={doSearch} disabled={loading}>Search</Button>
      </Stack>
      {loading && <Typography color="text.secondary">Searching…</Typography>}
      <Stack spacing={1}>
        {items.map((it) => {
          const eid = String(it.term_id || it.term);
          const ed = editing[eid];
          return (
            <Paper key={eid} sx={{ p: 2 }} variant="outlined">
              {ed ? (
                <Stack spacing={1}>
                  <TextField size="small" label="Term" value={ed.term} onChange={(e) => setEditing(s => ({ ...s, [eid]: { ...s[eid], term: e.target.value } }))} />
                  <TextField size="small" label="Description" value={ed.description} onChange={(e) => setEditing(s => ({ ...s, [eid]: { ...s[eid], description: e.target.value } }))} />
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="contained" onClick={async () => {
                      await fetch(buildApiUrl(`/api/v1/bcl/terms/${encodeURIComponent(String(it.term_id))}`), {
                        method: 'PUT',
                        headers: { ...headers, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ term: ed.term, description: ed.description }),
                      } as RequestInit);
                      setEditing(s => { const { [eid]: _, ...rest } = s; return rest; });
                      await doSearch();
                    }}>Save</Button>
                    <Button size="small" onClick={() => setEditing(s => { const { [eid]: _, ...rest } = s; return rest; })}>Cancel</Button>
                  </Stack>
                </Stack>
              ) : (
                <Stack spacing={1}>
                  <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
                    <Typography variant="subtitle1">{it.term}</Typography>
                    <Stack direction="row" spacing={1}>
                      <Button size="small" variant="outlined" onClick={() => setEditing(s => ({ ...s, [eid]: { term: it.term, description: it.description || '' } }))}>Edit</Button>
                      <Button size="small" color="error" variant="outlined" startIcon={<DeleteOutlineRounded />} onClick={async () => {
                        await fetch(buildApiUrl(`/api/v1/bcl/terms/${encodeURIComponent(String(it.term_id))}`), { method: 'DELETE', headers } as RequestInit);
                        await doSearch();
                      }}>Delete</Button>
                    </Stack>
                  </Stack>
                  <Typography variant="body2" color="text.secondary">{it.description}</Typography>
                </Stack>
              )}
            </Paper>
          );
        })}
      </Stack>
    </Stack>
  );
}



