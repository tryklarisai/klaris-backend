import React from 'react';
import { Box, Stack, TextField, Button, Typography, Paper, Alert, CircularProgress, Table, TableHead, TableRow, TableCell, TableBody, Divider, Chip } from '@mui/material';
import { buildApiUrl } from '../config';

interface RouteMeta {
  tool?: string;
  connector_id?: string;
  connector_type?: string;
}

interface DataPreview {
  columns: string[];
  rows: any[][];
}

interface ChatResponse {
  answer: string;
  route?: RouteMeta | null;
  data_preview?: DataPreview | null;
}

export default function ChatPage() {
  const [message, setMessage] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<ChatResponse | null>(null);
  const [draftAnswer, setDraftAnswer] = React.useState<string>('');
  const [thoughts, setThoughts] = React.useState<string[]>([]);
  const [tools, setTools] = React.useState<Array<{ type: 'start' | 'end'; tool: string; payload?: any }>>([]);

  async function sendMessage(e?: React.FormEvent) {
    e?.preventDefault();
    setError(null);
    setResult(null);
    setDraftAnswer('');
    setThoughts([]);
    setTools([]);
    const msg = message.trim();
    if (!msg) { setError('Please enter a question.'); return; }
    const token = window.localStorage.getItem('klaris_jwt');
    if (!token) { setError('You are not logged in. Please login to continue.'); return; }
    setLoading(true);
    try {
      const resp = await fetch(buildApiUrl('/api/v1/chat/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: msg }),
      });
      if (!resp.ok) {
        let detail = 'Chat stream request failed';
        try { detail = (await resp.text()) || detail; } catch {}
        throw new Error(detail);
      }
      if (!resp.body) throw new Error('No response body');
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split('\n\n');
        buffer = frames.pop() || '';
        for (const frame of frames) {
          const lines = frame.split('\n');
          const eventLine = lines.find(l => l.startsWith('event:')) || 'event: message';
          const dataLine = lines.find(l => l.startsWith('data:')) || 'data: {}';
          const type = eventLine.slice(6).trim();
          const json = dataLine.slice(5).trim();
          let data: any = {};
          try { data = json ? JSON.parse(json) : {}; } catch { data = {}; }
          if (type === 'ready') {
            // no-op
          } else if (type === 'token') {
            const t = (data && data.token) ? String(data.token) : '';
            if (t) setDraftAnswer(prev => prev + t);
          } else if (type === 'thought') {
            const log = (data && data.log) ? String(data.log) : '';
            if (log) setThoughts(prev => [...prev, log]);
          } else if (type === 'tool_start') {
            setTools(prev => [...prev, { type: 'start', tool: String(data?.tool || 'tool'), payload: data?.input }]);
          } else if (type === 'tool_end') {
            setTools(prev => [...prev, { type: 'end', tool: String(data?.tool || 'tool'), payload: data }]);
          } else if (type === 'final') {
            const answer = String(data?.answer || '');
            setResult({ answer } as ChatResponse);
          } else if (type === 'error') {
            setError(String(data || 'Stream error'));
          } else if (type === 'done') {
            setLoading(false);
            return;
          }
        }
      }
    } catch (e: any) {
      setError(e.message || 'Chat request failed');
    } finally {
      // loading is cleared on 'done' to keep spinner while streaming
    }
  }

  return (
    <Box>
      <Typography variant="h5" sx={{ mb: 2 }}>Analytics Chat</Typography>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <form onSubmit={sendMessage}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
            <TextField
              label="Ask a question"
              placeholder="e.g., What were the total orders last month by region?"
              fullWidth
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={loading}
            />
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? <CircularProgress size={20} /> : 'Ask'}
            </Button>
          </Stack>
        </form>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </Paper>

      {(draftAnswer || thoughts.length > 0 || tools.length > 0) && (
        <Box sx={{ mt: 3 }}>
          <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
            <Typography variant="subtitle1" gutterBottom>Streaming Answer</Typography>
            <Divider sx={{ mb: 2 }} />
            <Typography whiteSpace="pre-wrap">{draftAnswer}</Typography>
          </Paper>
          {(thoughts.length > 0 || tools.length > 0) && (
            <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
              <Typography variant="subtitle1" gutterBottom>Agent Progress</Typography>
              <Divider sx={{ mb: 2 }} />
              {thoughts.map((t, i) => (
                <Typography key={i} variant="body2" sx={{ color: 'text.secondary', mb: 0.5 }}>• {t}</Typography>
              ))}
              {tools.map((ev, i) => (
                <Typography key={`tool-${i}`} variant="caption" sx={{ display: 'block', color: 'text.disabled' }}>
                  [{ev.type === 'start' ? 'tool_start' : 'tool_end'}] {ev.tool}
                </Typography>
              ))}
            </Paper>
          )}
        </Box>
      )}

      {result && (
        <Box sx={{ mt: 3 }}>
          {/* Route metadata */}
          {result.route && (
            <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
              <Typography variant="subtitle1" gutterBottom>Tool Route</Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap">
                {result.route.tool && <Chip size="small" label={`tool: ${result.route.tool}`} />}
                {result.route.connector_type && <Chip size="small" label={`type: ${result.route.connector_type}`} />}
                {result.route.connector_id && <Chip size="small" label={`connector: ${result.route.connector_id}`} />}
              </Stack>
            </Paper>
          )}

          {/* Assistant answer */}
          <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
            <Typography variant="subtitle1" gutterBottom>Assistant Answer</Typography>
            <Divider sx={{ mb: 2 }} />
            <Typography whiteSpace="pre-wrap">{result.answer || ''}</Typography>
          </Paper>

          {/* Data preview */}
          {result.data_preview && result.data_preview.columns?.length > 0 && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle1" gutterBottom>Data Preview</Typography>
              <Divider sx={{ mb: 2 }} />
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {result.data_preview.columns.map((c, idx) => (
                        <TableCell key={idx}>{c}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {result.data_preview.rows.map((r, rIdx) => (
                      <TableRow key={rIdx}>
                        {r.map((v, cIdx) => (
                          <TableCell key={cIdx}>{String(v)}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </Paper>
          )}
        </Box>
      )}
    </Box>
  );
}
