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
  Alert,
  CircularProgress,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
} from "@mui/material";
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import SearchIcon from '@mui/icons-material/Search';
import { buildApiUrl } from "../config";
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';
import EditIcon from '@mui/icons-material/Edit';

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
  const [selectedFiles, setSelectedFiles] = React.useState<File[]>([]);

  function handleFileSelection(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (files) {
      setSelectedFiles(Array.from(files));
      setGlossaryResult(null); // Clear previous results
    }
  }

  function removeFile(index: number) {
    setSelectedFiles(files => files.filter((_, i) => i !== index));
  }

  async function handleImportGlossary() {
    if (selectedFiles.length === 0) return;
    
    const file = selectedFiles[0]; // For now, import the first file
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
      if (!data.error) {
        setSelectedFiles([]); // Clear files on successful import
        if (glossaryInputRef.current) {
          glossaryInputRef.current.value = ''; // Reset file input
        }
      }
    } catch (e) {
      setGlossaryResult({ error: String(e) });
    } finally {
      setGlossaryLoading(false);
    }
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" sx={{ mb: 1, fontWeight: 600 }}>Business Context</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
        Manage business glossary terms and definitions to provide context for your data
      </Typography>

      <Accordion defaultExpanded sx={{ mb: 2 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ fontWeight: 500 }}>
            {selectedFiles.length > 0 ? 'Import Business Glossary' : 'Import Business Glossary'}
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          {selectedFiles.length === 0 ? (
            <Paper variant="outlined" sx={{ p: 3, textAlign: 'center', bgcolor: 'grey.50' }}>
              <Stack spacing={2} alignItems="center">
                <UploadFileIcon sx={{ fontSize: 48, color: 'text.secondary' }} />
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Upload CSV, Excel (.xlsx), or XLS files
                </Typography>
                <input 
                  ref={glossaryInputRef} 
                  type="file" 
                  accept=".csv,.xlsx,.xls" 
                  style={{ display: 'none' }} 
                  id="glossary-file-input"
                  onChange={handleFileSelection}
                  multiple
                />
                <label htmlFor="glossary-file-input">
                  <Button 
                    variant="contained" 
                    component="span"
                    startIcon={<UploadFileIcon />}
                    size="large"
                  >
                    Choose Files
                  </Button>
                </label>
              </Stack>
            </Paper>
          ) : (
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
                    Selected Files ({selectedFiles.length})
                  </Typography>
                  <label htmlFor="glossary-file-input">
                    <Button 
                      variant="outlined" 
                      component="span"
                      startIcon={<UploadFileIcon />}
                      size="small"
                    >
                      Choose Different Files
                    </Button>
                  </label>
                  <input 
                    ref={glossaryInputRef} 
                    type="file" 
                    accept=".csv,.xlsx,.xls" 
                    style={{ display: 'none' }} 
                    id="glossary-file-input"
                    onChange={handleFileSelection}
                    multiple
                  />
                </Stack>
                <List dense>
                  {selectedFiles.map((file, index) => (
                    <ListItem key={index} sx={{ px: 0 }}>
                      <ListItemText 
                        primary={file.name}
                        secondary={`${(file.size / 1024).toFixed(1)} KB`}
                      />
                      <ListItemSecondaryAction>
                        <IconButton 
                          edge="end" 
                          onClick={() => removeFile(index)}
                          size="small"
                          color="error"
                        >
                          <DeleteOutlineRounded />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                </List>
              </Paper>
              <Box sx={{ textAlign: 'center' }}>
                <Button 
                  variant="contained" 
                  onClick={handleImportGlossary} 
                  disabled={glossaryLoading || selectedFiles.length === 0}
                  startIcon={glossaryLoading ? <CircularProgress size={20} /> : <UploadFileIcon />}
                  size="large"
                >
                  {glossaryLoading ? 'Importing...' : 'Import Glossary'}
                </Button>
              </Box>
            </Stack>
          )}
          {!!glossaryResult && (
            <Box sx={{ mt: 2 }}>
              {glossaryResult.error ? (
                <Alert severity="error">
                  Error: {glossaryResult.error}
                </Alert>
              ) : (
                <Alert severity="success">
                  Successfully imported: {glossaryResult.terms_upserted} terms from {glossaryResult.rows_processed} rows
                </Alert>
              )}
            </Box>
          )}
        </AccordionDetails>
      </Accordion>

      <Accordion defaultExpanded sx={{ mb: 2 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ fontWeight: 500 }}>Glossary Terms</Typography>
        </AccordionSummary>
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
    <Stack spacing={3}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
          <TextField 
            size="small" 
            label="Search terms" 
            placeholder="Search business terms..."
            value={q} 
            onChange={(e) => setQ(e.target.value)} 
            sx={{ flexGrow: 1, minWidth: 280 }}
          />
          <TextField 
            size="small" 
            label="Results limit" 
            type="number" 
            value={topK} 
            onChange={(e) => setTopK(Math.max(1, Number(e.target.value || 20)))} 
            sx={{ width: 140 }}
          />
          <Button 
            variant="contained" 
            onClick={doSearch} 
            disabled={loading}
            startIcon={loading ? <CircularProgress size={20} /> : <SearchIcon />}
          >
            {loading ? 'Searching...' : 'Search'}
          </Button>
        </Stack>
      </Paper>
      
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Stack spacing={2}>
          {items.length === 0 ? (
            <Paper sx={{ p: 4, textAlign: 'center' }}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                No glossary terms found
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {q ? 'Try adjusting your search terms or import a business glossary file.' : 'Import a business glossary file to get started.'}
              </Typography>
            </Paper>
          ) : (
            items.map((it) => {
              const eid = String(it.term_id || it.term);
              const ed = editing[eid];
              return (
                <Paper key={eid} sx={{ p: 3, border: '1px solid', borderColor: 'divider' }} elevation={0}>
                  {ed ? (
                    <Stack spacing={2}>
                      <Typography variant="h6" sx={{ fontWeight: 500 }}>Edit Term</Typography>
                      <TextField 
                        size="small" 
                        label="Term" 
                        value={ed.term} 
                        onChange={(e) => setEditing(s => ({ ...s, [eid]: { ...s[eid], term: e.target.value } }))}
                        fullWidth
                      />
                      <TextField 
                        size="small" 
                        label="Description" 
                        value={ed.description} 
                        onChange={(e) => setEditing(s => ({ ...s, [eid]: { ...s[eid], description: e.target.value } }))}
                        multiline
                        rows={3}
                        fullWidth
                      />
                      <Stack direction="row" spacing={1}>
                        <Button size="small" variant="contained" onClick={async () => {
                          await fetch(buildApiUrl(`/api/v1/bcl/terms/${encodeURIComponent(String(it.term_id))}`), {
                            method: 'PUT',
                            headers: { ...headers, 'Content-Type': 'application/json' },
                            body: JSON.stringify({ term: ed.term, description: ed.description }),
                          } as RequestInit);
                          setEditing(s => { const { [eid]: _, ...rest } = s; return rest; });
                          await doSearch();
                        }}>Save Changes</Button>
                        <Button size="small" variant="outlined" onClick={() => setEditing(s => { const { [eid]: _, ...rest } = s; return rest; })}>Cancel</Button>
                      </Stack>
                    </Stack>
                  ) : (
                    <Stack spacing={2}>
                      <Stack direction="row" alignItems="flex-start" justifyContent="space-between">
                        <Box sx={{ flexGrow: 1 }}>
                          <Typography variant="h6" sx={{ fontWeight: 500, mb: 1 }}>
                            {it.term}
                          </Typography>
                          <Typography variant="body1" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                            {it.description || 'No description provided'}
                          </Typography>
                        </Box>
                        <Stack direction="row" spacing={1} sx={{ ml: 2 }}>
                          <Button 
                            size="small" 
                            variant="outlined" 
                            startIcon={<EditIcon />}
                            onClick={() => setEditing(s => ({ ...s, [eid]: { term: it.term, description: it.description || '' } }))}
                          >
                            Edit
                          </Button>
                          <Button 
                            size="small" 
                            color="error" 
                            variant="outlined" 
                            startIcon={<DeleteOutlineRounded />} 
                            onClick={async () => {
                              if (window.confirm(`Are you sure you want to delete "${it.term}"?`)) {
                                await fetch(buildApiUrl(`/api/v1/bcl/terms/${encodeURIComponent(String(it.term_id))}`), { method: 'DELETE', headers } as RequestInit);
                                await doSearch();
                              }
                            }}
                          >
                            Delete
                          </Button>
                        </Stack>
                      </Stack>
                      {it.term_id && (
                        <Chip label={`ID: ${it.term_id}`} size="small" variant="outlined" sx={{ alignSelf: 'flex-start' }} />
                      )}
                    </Stack>
                  )}
                </Paper>
              );
            })
          )}
        </Stack>
      )}
    </Stack>
  );
}



