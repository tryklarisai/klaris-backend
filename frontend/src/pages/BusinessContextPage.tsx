import React from 'react';
import { Box, Typography, Accordion, AccordionSummary, AccordionDetails, Button, CircularProgress, Alert, Stack, TextField, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { buildApiUrl } from '../config';

const API_URL = buildApiUrl('');

export default function BusinessContextPage() {
  const [tenantId, setTenantId] = React.useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [urlValue, setUrlValue] = React.useState('');
  const [glossUrlValue, setGlossUrlValue] = React.useState('');
  const [message, setMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    const tStr = window.localStorage.getItem('klaris_tenant');
    if (tStr) setTenantId(JSON.parse(tStr).tenant_id);
  }, []);

  async function uploadUrl(type: 'url'|'glossary') {
    if (!tenantId) return;
    setUploading(true); setMessage(null);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      const form = new FormData();
      form.append('type', type);
      form.append('url', type === 'url' ? urlValue : glossUrlValue);
      const resp = await fetch(`${API_URL}/tenants/${tenantId}/business-context/sources`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result?.detail || 'Upload failed');
      setMessage('Source created');
    } catch (e: any) {
      setMessage(e.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  }

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>Business Context</Typography>
      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Sources</AccordionSummary>
        <AccordionDetails>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <TextField size="small" placeholder="Add documentation URL" sx={{ width: 420 }} value={urlValue} onChange={(e) => setUrlValue(e.target.value)} />
            <Button variant="contained" disabled={uploading || !urlValue} onClick={() => uploadUrl('url')}>{uploading ? 'Uploading…' : 'Add URL'}</Button>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField size="small" placeholder="Glossary sheet URL (.xlsx)" sx={{ width: 420 }} value={glossUrlValue} onChange={(e) => setGlossUrlValue(e.target.value)} />
            <Button variant="outlined" disabled={uploading || !glossUrlValue} onClick={() => uploadUrl('glossary')}>{uploading ? 'Uploading…' : 'Add Glossary URL'}</Button>
          </Stack>
          {message && <Alert severity={message.includes('failed') ? 'error' : 'success'} sx={{ mt: 1 }}>{message}</Alert>}
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Glossary</AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary">Glossary editor will appear here (M1 skeleton).</Typography>
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Enrich with AI</AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary">Enrichment trigger and suggestions will appear here (M1).</Typography>
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Editor</AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary">Business Context editor (terms, mappings) will appear here.</Typography>
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>Results</AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary">Latest business context will appear here.</Typography>
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}


