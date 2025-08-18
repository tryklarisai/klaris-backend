import React from 'react';
import { Box, Stack, Paper, Typography, Alert, CircularProgress, Table, TableHead, TableRow, TableCell, TableBody, Divider, Chip, IconButton, InputBase, Tooltip, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import SendRounded from '@mui/icons-material/SendRounded';
import MicRounded from '@mui/icons-material/MicRounded';
import AttachFileRounded from '@mui/icons-material/AttachFileRounded';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import BoltRounded from '@mui/icons-material/BoltRounded';
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
  const theme = useTheme();
  const isMobile = useMediaQuery('(max-width:900px)');

  const [message, setMessage] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<ChatResponse | null>(null);
  const [draftAnswer, setDraftAnswer] = React.useState<string>('');
  const [thoughts, setThoughts] = React.useState<string[]>([]);
  const [tools, setTools] = React.useState<Array<{ type: 'start' | 'end'; tool: string; payload?: any }>>([]);

  const suggestions = [
    'What were the total orders last month by region?',
    'Top 5 products by revenue this quarter',
    'Trend of weekly active users vs CAC',
  ];

  function applySuggestion(text: string, autoSend = false) {
    setMessage(text);
    if (autoSend && !loading) {
      setTimeout(() => sendMessage(), 0);
    }
  }

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
            const route = (data && data.route) ? data.route : null;
            const data_preview = (data && data.data_preview) ? data.data_preview : null;
            setResult({ answer, route, data_preview } as ChatResponse);
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

  const gradientBg = theme.palette.mode === 'light'
    ? `radial-gradient(1200px 600px at 0% -10%, rgba(25,118,210,0.10), transparent 60%),
       radial-gradient(1000px 500px at 100% 0%, rgba(156,39,176,0.10), transparent 60%)`
    : `radial-gradient(1200px 600px at 0% -10%, rgba(25,118,210,0.18), transparent 60%),
       radial-gradient(1000px 500px at 100% 0%, rgba(255,255,255,0.06), transparent 60%)`;

  const glassBg = theme.palette.mode === 'light' ? 'rgba(255,255,255,0.65)' : 'rgba(18,26,46,0.55)';

  return (
    <Box sx={{ position: 'relative', py: { xs: 2, md: 4 } }}>
      {/* Background gradients */}
      <Box sx={{ position: 'absolute', inset: 0, background: gradientBg, pointerEvents: 'none' }} />

      <Box sx={{ position: 'relative', maxWidth: 1100, mx: 'auto', px: { xs: 0, md: 1 } }}>
        {/* Hero / Header */}
        <Stack spacing={1.2} sx={{ mb: 2, px: { xs: 1, md: 0 } }}>
          <Typography variant="h4" fontWeight={800}>
            Klaris Copilot
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Ask questions about your data. The agent streams insights and uses your connectors to fetch real numbers.
          </Typography>
        </Stack>

        {/* Glass container */}
        <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, borderRadius: 4, backgroundColor: glassBg, backdropFilter: 'blur(12px)', border: '1px solid', borderColor: 'divider' }}>
          {/* Suggestions */}
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
            {suggestions.map((s, i) => (
              <Chip
                key={i}
                icon={<AutoAwesomeRounded fontSize="small" />}
                label={s}
                onClick={() => applySuggestion(s, true)}
                sx={{
                  bgcolor: theme.palette.mode === 'light' ? 'rgba(25,118,210,0.08)' : 'rgba(255,255,255,0.06)',
                  '&:hover': { bgcolor: theme.palette.mode === 'light' ? 'rgba(25,118,210,0.14)' : 'rgba(255,255,255,0.10)' },
                }}
                size="small"
              />
            ))}
          </Stack>

          {/* Messages / Streaming area */}
          {(draftAnswer || result || error || thoughts.length > 0 || tools.length > 0) ? (
            <Box>
              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

              {/* Assistant streaming bubble */}
              {draftAnswer && (
                <Box sx={{ display: 'flex', mb: 2 }}>
                  <Paper elevation={0} sx={{ p: 2, borderRadius: 3, bgcolor: theme.palette.mode === 'light' ? 'rgba(25,118,210,0.06)' : 'rgba(255,255,255,0.04)', border: '1px solid', borderColor: 'divider', flex: 1 }}>
                    <Typography variant="overline" sx={{ display: 'block', color: 'text.secondary', mb: 0.5 }}>
                      Assistant is typing…
                    </Typography>
                    <Typography whiteSpace="pre-wrap">{draftAnswer}</Typography>
                  </Paper>
                </Box>
              )}

              {/* Final assistant answer */}
              {result?.answer && (
                <Box sx={{ display: 'flex', mb: 2 }}>
                  <Paper elevation={0} sx={{ p: 2, borderRadius: 3, bgcolor: theme.palette.mode === 'light' ? 'background.paper' : 'rgba(255,255,255,0.04)', border: '1px solid', borderColor: 'divider', flex: 1 }}>
                    <Typography variant="subtitle1" gutterBottom>Answer</Typography>
                    <Divider sx={{ mb: 1.5 }} />
                    <Typography whiteSpace="pre-wrap">{result.answer}</Typography>
                  </Paper>
                </Box>
              )}

              {/* Route metadata */}
              {result?.route && (
                <Paper variant="outlined" sx={{ p: 2, mb: 2, borderRadius: 3 }}>
                  <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                    <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <BoltRounded fontSize="small" color="primary" /> Tool Route
                    </Typography>
                    <Box sx={{ flex: 1 }} />
                    {result.route.tool && <Chip size="small" label={`tool: ${result.route.tool}`} />}
                    {result.route.connector_type && <Chip size="small" label={`type: ${result.route.connector_type}`} />}
                    {result.route.connector_id && <Chip size="small" label={`connector: ${result.route.connector_id}`} />}
                  </Stack>
                </Paper>
              )}

              {/* Agent Progress */}
              {(thoughts.length > 0 || tools.length > 0) && (
                <Paper variant="outlined" sx={{ p: 2, mb: 2, borderRadius: 3 }}>
                  <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                    <BoltRounded fontSize="small" color="primary" /> Agent Progress
                  </Typography>
                  <Divider sx={{ mb: 1.5 }} />
                  <Box>
                    {thoughts.map((t, i) => (
                      <Typography key={i} variant="body2" sx={{ color: 'text.secondary', mb: 0.5 }}>• {t}</Typography>
                    ))}
                    {tools.map((ev, i) => (
                      <Typography key={`tool-${i}`} variant="caption" sx={{ display: 'block', color: 'text.disabled' }}>
                        [{ev.type === 'start' ? 'tool_start' : 'tool_end'}] {ev.tool}
                      </Typography>
                    ))}
                  </Box>
                </Paper>
              )}

              {/* Data preview */}
              {result?.data_preview && result.data_preview.columns?.length > 0 && (
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                  <Typography variant="subtitle2" gutterBottom>Data Preview</Typography>
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
          ) : (
            // Empty state
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="h6" sx={{ mb: 1.5 }}>Start a conversation</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Try one of the suggested prompts above or ask anything about your connected data.
              </Typography>
            </Box>
          )}

          {/* Input bar */}
          <Paper
            component="form"
            onSubmit={sendMessage}
            elevation={0}
            sx={{
              mt: 2,
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              p: 1,
              borderRadius: 999,
              bgcolor: theme.palette.background.paper,
              border: '1px solid',
              borderColor: 'divider',
              boxShadow: theme.palette.mode === 'light' ? '0 8px 32px rgba(16,24,40,0.06)' : '0 8px 32px rgba(0,0,0,0.5)'
            }}
          >
            <Tooltip title="Attach (coming soon)">
              <span>
                <IconButton size="small" disabled={loading}>
                  <AttachFileRounded fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <InputBase
              placeholder="Ask anything about your data…"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={loading}
              sx={{ ml: 1, flex: 1, fontSize: 16 }}
            />
            <Tooltip title="Voice (coming soon)">
              <span>
                <IconButton size="small" disabled>
                  <MicRounded fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title="Send">
              <span>
                <IconButton type="submit" color="primary" disabled={loading || !message.trim()}>
                  {loading ? <CircularProgress size={20} /> : <SendRounded />}
                </IconButton>
              </span>
            </Tooltip>
          </Paper>
        </Paper>
      </Box>
    </Box>
  );
}
