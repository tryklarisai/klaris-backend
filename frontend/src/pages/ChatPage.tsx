import React from 'react';
import { Box, Stack, Paper, Typography, Alert, CircularProgress, Table, TableHead, TableRow, TableCell, TableBody, Divider, Chip, IconButton, InputBase, Tooltip, useMediaQuery, Button, Select, MenuItem, Collapse, Fab, TableContainer } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import SendRounded from '@mui/icons-material/SendRounded';
import MicRounded from '@mui/icons-material/MicRounded';
import AttachFileRounded from '@mui/icons-material/AttachFileRounded';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import BoltRounded from '@mui/icons-material/BoltRounded';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';
import AddRounded from '@mui/icons-material/AddRounded';
import KeyboardDoubleArrowDownRounded from '@mui/icons-material/KeyboardDoubleArrowDownRounded';
import { buildApiUrl } from '../config';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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
  const params = useParams();
  const navigate = useNavigate();

  const [message, setMessage] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<ChatResponse | null>(null);
  const [draftAnswer, setDraftAnswer] = React.useState<string>('');
  const [thoughts, setThoughts] = React.useState<string[]>([]);
  const [tools, setTools] = React.useState<Array<{ type: 'start' | 'end'; tool: string; payload?: any }>>([]);

  // Thread state
  const [threads, setThreads] = React.useState<string[]>([]);
  const [threadId, setThreadId] = React.useState<string | null>(null);
  const [threadsLoading, setThreadsLoading] = React.useState(false);
  const [threadsPanelOpen, setThreadsPanelOpen] = React.useState<boolean>(true);
  const [showScrollToBottom, setShowScrollToBottom] = React.useState<boolean>(false);
  const threadsFetchSeq = React.useRef(0);

  React.useEffect(() => {
    setThreadsPanelOpen(!isMobile);
  }, [isMobile]);

  // Sync local threadId with route param
  React.useEffect(() => {
    const tid = (params as any)?.threadId ? String((params as any).threadId) : null;
    setThreadId(tid);
  }, [params]);

  const scrollToBottom = React.useCallback(() => {
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' });
  }, []);

  React.useEffect(() => {
    const onScroll = () => {
      const scrollPos = window.scrollY + window.innerHeight;
      const docHeight = document.documentElement.scrollHeight;
      const threshold = 120;
      setShowScrollToBottom(scrollPos < docHeight - threshold);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true } as any);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

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
    if (!threadId) { setError('Create or select a thread to start chatting.'); return; }
    setLoading(true);
    try {
      const resp = await fetch(buildApiUrl('/api/v1/chat/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: msg, thread_id: threadId || undefined }),
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

  // Threads API helpers
  const fetchThreads = React.useCallback(async () => {
    const seq = ++threadsFetchSeq.current;
    setThreadsLoading(true);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      if (!token) { return; }
      const url = buildApiUrl(`/api/v1/chat/threads?t=${Date.now()}`);
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        cache: 'no-store',
      } as RequestInit);
      if (!resp.ok) return;
      const data = await resp.json();
      const list = Array.isArray(data?.threads) ? data.threads as string[] : [];
      if (seq === threadsFetchSeq.current) {
        setThreads(list);
        // If current threadId is gone, clear selection and navigate to /chat
        if (threadId && !list.includes(threadId)) {
          setThreadId(null);
          navigate('/chat');
        }
      }
    } catch (e) {
      // ignore
    } finally {
      if (seq === threadsFetchSeq.current) setThreadsLoading(false);
    }
  }, [threadId, navigate]);

  React.useEffect(() => { fetchThreads(); }, [fetchThreads]);

  async function handleCreateThread() {
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      if (!token) { setError('You are not logged in. Please login to continue.'); return; }
      const resp = await fetch(buildApiUrl('/api/v1/chat/threads'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) { setError('Failed to create thread'); return; }
      const data = await resp.json();
      const tid = String(data?.thread_id || '');
      if (tid) {
        setThreadId(tid);
        navigate(`/chat/${encodeURIComponent(tid)}`);
      }
      await fetchThreads();
      if (tid) {
        window.dispatchEvent(new CustomEvent('chat:threads:changed', { detail: { type: 'created', id: tid } }));
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to create thread');
    }
  }

  async function handleDeleteThread() {
    if (!threadId) return;
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      if (!token) { setError('You are not logged in. Please login to continue.'); return; }
      const resp = await fetch(buildApiUrl(`/api/v1/chat/threads/${encodeURIComponent(threadId)}`), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) { setError('Failed to delete thread'); return; }
      const deletedId = threadId;
      setThreadId(null);
      navigate('/chat');
      await fetchThreads();
      if (deletedId) {
        window.dispatchEvent(new CustomEvent('chat:threads:changed', { detail: { type: 'deleted', id: deletedId } }));
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to delete thread');
    }
  }

  async function deleteThreadById(id: string) {
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      if (!token) { setError('You are not logged in. Please login to continue.'); return; }
      const resp = await fetch(buildApiUrl(`/api/v1/chat/threads/${encodeURIComponent(id)}`), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) { setError('Failed to delete thread'); return; }
      if (threadId === id) {
        setThreadId(null);
        navigate('/chat');
      }
      await fetchThreads();
      window.dispatchEvent(new CustomEvent('chat:threads:changed', { detail: { type: 'deleted', id } }));
    } catch (e: any) {
      setError(e?.message || 'Failed to delete thread');
    }
  }

  const gradientBg = theme.palette.mode === 'light'
    ? `radial-gradient(1200px 600px at 0% -10%, rgba(25,118,210,0.10), transparent 60%),
       radial-gradient(1000px 500px at 100% 0%, rgba(156,39,176,0.10), transparent 60%)`
    : `radial-gradient(1200px 600px at 0% -10%, rgba(25,118,210,0.18), transparent 60%),
       radial-gradient(1000px 500px at 100% 0%, rgba(255,255,255,0.06), transparent 60%)`;

  const glassBg = theme.palette.mode === 'light' ? 'rgba(255,255,255,0.65)' : 'rgba(18,26,46,0.55)';

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

        <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, borderRadius: 4, backgroundColor: glassBg, backdropFilter: 'blur(12px)', border: '1px solid', borderColor: 'divider' }}>
          {!threadId ? (
            <Box sx={{ minHeight: 280, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Stack spacing={1.5} alignItems="center">
                <Typography variant="body1" color="text.secondary">No thread selected</Typography>
                <Button variant="contained" startIcon={<AddRounded />} onClick={handleCreateThread} disabled={loading || threadsLoading}>
                  Create thread
                </Button>
              </Stack>
            </Box>
          ) : (
            <Stack direction="row" spacing={2} sx={{ minWidth: 0 }}>
              {/* Sidebar: Threads (mobile-only; desktop threads are in main left nav) */}
              <Box sx={{ width: 260, display: { xs: 'block', md: 'none' } }}>
                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Typography variant="subtitle2">Threads</Typography>
                    <IconButton size="small" onClick={() => setThreadsPanelOpen(v => !v)}>
                      {threadsPanelOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                    </IconButton>
                  </Stack>
                  <Collapse in={threadsPanelOpen} unmountOnExit>
                    <Stack spacing={1} sx={{ mt: 1 }}>
                      <Button startIcon={<AddRounded />} size="small" variant="outlined" onClick={handleCreateThread} disabled={loading || threadsLoading}>
                        New thread
                      </Button>
                      <Divider />
                      {threadsLoading ? (
                        <Typography variant="caption" color="text.secondary">Loading…</Typography>
                      ) : threads.length === 0 ? (
                        <Stack spacing={1} sx={{ py: 1 }}>
                          <Typography variant="body2" color="text.secondary">No threads yet.</Typography>
                          <Button size="small" variant="contained" onClick={handleCreateThread}>Start thread</Button>
                        </Stack>
                      ) : (
                        <Box>
                          {threads.map((t) => (
                            <Stack key={t} direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
                              <Button
                                variant={t === threadId ? 'contained' : 'text'}
                                size="small"
                                onClick={() => navigate(`/chat/${encodeURIComponent(t)}`)}
                                sx={{ justifyContent: 'flex-start', textTransform: 'none', flex: 1, overflow: 'hidden' }}
                              >
                                <Typography noWrap maxWidth={180} variant="caption">{t}</Typography>
                              </Button>
                              <IconButton size="small" color="error" onClick={() => deleteThreadById(t)}>
                                <DeleteOutlineRounded fontSize="small" />
                              </IconButton>
                            </Stack>
                          ))}
                        </Box>
                      )}
                    </Stack>
                  </Collapse>
                </Paper>
              </Box>

              {/* Main Chat */}
              <Box sx={{ flex: 1, minWidth: 0 }}>
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
                      <Box sx={{ display: 'flex', mb: 2, minWidth: 0 }}>
                        <Paper elevation={0} sx={{ p: 2, borderRadius: 3, bgcolor: theme.palette.mode === 'light' ? 'rgba(25,118,210,0.06)' : 'rgba(255,255,255,0.04)', border: '1px solid', borderColor: 'divider', flex: 1, minWidth: 0, maxWidth: '100%' }}>
                          <Typography variant="overline" sx={{ display: 'block', color: 'text.secondary', mb: 0.5 }}>
                            Assistant is typing…
                          </Typography>
                          <Box sx={{
                            overflowX: 'auto',
                            maxWidth: '100%',
                            wordBreak: 'break-word',
                            overflowWrap: 'anywhere',
                            '& p': { m: 0 },
                            '& pre': { p: 1, borderRadius: 1, overflow: 'auto', maxWidth: '100%', bgcolor: theme.palette.mode === 'light' ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.06)' },
                            '& code': { whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
                            '& table': { display: 'block', width: '100%', tableLayout: 'fixed', borderCollapse: 'collapse' },
                            '& th, & td': { border: `1px solid ${theme.palette.divider}`, padding: '4px 8px', verticalAlign: 'top', wordBreak: 'break-word', overflowWrap: 'anywhere', whiteSpace: 'normal' },
                            '& img': { maxWidth: '100%', height: 'auto' }
                          }}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {draftAnswer}
                            </ReactMarkdown>
                          </Box>
                        </Paper>
                      </Box>
                    )}

                    {/* Final assistant answer */}
                    {result?.answer && (
                      <Box sx={{ display: 'flex', mb: 2, minWidth: 0 }}>
                        <Paper elevation={0} sx={{ p: 2, borderRadius: 3, bgcolor: theme.palette.mode === 'light' ? 'background.paper' : 'rgba(255,255,255,0.04)', border: '1px solid', borderColor: 'divider', flex: 1, minWidth: 0, maxWidth: '100%' }}>
                          <Typography variant="subtitle1" gutterBottom>Answer</Typography>
                          <Divider sx={{ mb: 1.5 }} />
                          <Box sx={{
                            overflowX: 'auto',
                            maxWidth: '100%',
                            wordBreak: 'break-word',
                            overflowWrap: 'anywhere',
                            '& pre': { p: 1, borderRadius: 1, overflow: 'auto', maxWidth: '100%', bgcolor: theme.palette.mode === 'light' ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.06)' },
                            '& code': { whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
                            '& table': { display: 'block', width: '100%', tableLayout: 'fixed', borderCollapse: 'collapse' },
                            '& th, & td': { border: `1px solid ${theme.palette.divider}`, padding: '4px 8px', verticalAlign: 'top', wordBreak: 'break-word', overflowWrap: 'anywhere', whiteSpace: 'normal' },
                            '& img': { maxWidth: '100%', height: 'auto' }
                          }}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {result.answer}
                            </ReactMarkdown>
                          </Box>
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
                        <TableContainer sx={{ overflowX: 'auto', maxWidth: '100%' }}>
                          <Table size="small" sx={{ minWidth: 640, tableLayout: 'auto' }}>
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
                        </TableContainer>
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
                    placeholder={threadId ? 'Ask anything about your data…' : 'Create a thread to start chatting…'}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    disabled={loading || !threadId}
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
                      <IconButton type="submit" color="primary" disabled={loading || !message.trim() || !threadId}>
                        {loading ? <CircularProgress size={20} /> : <SendRounded />}
                      </IconButton>
                    </span>
                  </Tooltip>
                </Paper>
              </Box>
            </Stack>
          )}
        </Paper>
        {showScrollToBottom && !!threadId && (
          <Fab color="primary" size="small" onClick={scrollToBottom} sx={{ position: 'fixed', bottom: 24, right: 24, zIndex: 1300 }}>
            <KeyboardDoubleArrowDownRounded />
          </Fab>
        )}
      </Box>
    </Box>
  );
}
