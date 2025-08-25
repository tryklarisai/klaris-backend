import React from 'react';
import { Box, Stack, Paper, Typography, Alert, CircularProgress, Table, TableHead, TableRow, TableCell, TableBody, Divider, Chip, IconButton, InputBase, Tooltip, useMediaQuery, Button, Select, MenuItem, Collapse, Fab, TableContainer, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
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
import { keyframes } from '@mui/system';
import ChartRenderer from '../components/ChartRenderer';
import AttachedFilesContext from '../components/AttachedFilesContext';
import html2pdf from 'html2pdf.js';
import ThumbUpOffAlt from '@mui/icons-material/ThumbUpOffAlt';
import ThumbDownOffAlt from '@mui/icons-material/ThumbDownOffAlt';
import IosShare from '@mui/icons-material/IosShare';

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
  charts?: Array<{ title?: string | null; type?: string; spec: any }> | null;
}

type ThreadItem = { thread_id: string; title?: string | null };

// Simple bounce animation for the three streaming dots
const bounce = keyframes`
  0%, 80%, 100% { transform: scale(0); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
`;

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
  const [lastUserMessage, setLastUserMessage] = React.useState<string>('');
  const [detailsOpen, setDetailsOpen] = React.useState<boolean>(false);
  const [answerComplete, setAnswerComplete] = React.useState<boolean>(false);
  const answerRef = React.useRef<HTMLDivElement | null>(null);
  const [chartsRendered, setChartsRendered] = React.useState(0);
  const chartsTotal = Array.isArray(result?.charts) ? result!.charts!.length : 0;
  const [exporting, setExporting] = React.useState(false);
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [previewHtml, setPreviewHtml] = React.useState<string>("");
  const [previewLoading, setPreviewLoading] = React.useState(false);

  // Thread state
  const [threads, setThreads] = React.useState<ThreadItem[]>([]);
  const [threadId, setThreadId] = React.useState<string | null>(null);
  const [threadsLoading, setThreadsLoading] = React.useState(false);
  const [threadsPanelOpen, setThreadsPanelOpen] = React.useState<boolean>(true);
  const [showScrollToBottom, setShowScrollToBottom] = React.useState<boolean>(false);
  const threadsFetchSeq = React.useRef(0);

  const getThreadTitle = React.useCallback((t: ThreadItem) => {
    const title = (t.title ? String(t.title) : '').trim();
    return title || `Thread - ${t.thread_id.slice(0, 8)}`;
  }, []);

  React.useEffect(() => {
    setThreadsPanelOpen(!isMobile);
  }, [isMobile]);

  React.useEffect(() => {
    // Reset charts rendered counter when result changes
    setChartsRendered(0);
  }, [result?.charts]);

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
    setAnswerComplete(false);
    const msg = message.trim();
    if (!msg) { setError('Please enter a question.'); return; }
    const token = window.localStorage.getItem('klaris_jwt');
    if (!token) { setError('You are not logged in. Please login to continue.'); return; }
    if (!threadId) { setError('Create or select a thread to start chatting.'); return; }
    // Clear the input immediately on send
    setLastUserMessage(msg);
    setMessage('');
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
            const charts = Array.isArray(data?.charts) ? data.charts : null;
            console.log('Chat final event:', { answer, route, data_preview, charts });
            setResult({ answer, route, data_preview, charts } as ChatResponse);
          } else if (type === 'error') {
            setError(String(data || 'Stream error'));
          } else if (type === 'done') {
            setLoading(false);
            setAnswerComplete(true);
            // Refresh threads to pick up server-side auto-title
            try { await fetchThreads(); } catch {}
            try { window.dispatchEvent(new CustomEvent('chat:threads:changed', { detail: { type: 'updated', id: threadId } })); } catch {}
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
      let list: ThreadItem[] = [];
      if (Array.isArray(data?.threads)) {
        const arr: any[] = data.threads as any[];
        if (arr.length > 0 && typeof arr[0] === 'object') {
          list = arr.map((r: any) => ({ thread_id: String(r.thread_id), title: r?.title ?? null }));
        } else {
          list = (arr as string[]).map((id) => ({ thread_id: String(id), title: null }));
        }
      }
      if (seq === threadsFetchSeq.current) {
        setThreads(list);
        // If current threadId is gone, clear selection and navigate to /chat
        const ids = new Set(list.map((t) => t.thread_id));
        if (threadId && !ids.has(threadId)) {
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

  async function exportPdf() {
    try {
      if (!answerRef.current) return;
      setExporting(true);
      // Wait briefly for charts to render if any
      const start = Date.now();
      const timeoutMs = 2000;
      while (Array.isArray(result?.charts) && chartsRendered < chartsTotal && (Date.now() - start) < timeoutMs) {
        await new Promise(r => setTimeout(r, 100));
      }
      const threadShort = (threadId || '').slice(0, 8);
      const ts = new Date();
      const y = ts.getFullYear();
      const m = String(ts.getMonth() + 1).padStart(2, '0');
      const d = String(ts.getDate()).padStart(2, '0');
      const hh = String(ts.getHours()).padStart(2, '0');
      const mm = String(ts.getMinutes()).padStart(2, '0');
      const filename = `klaris-answer-${threadShort || 'chat'}-${y}${m}${d}-${hh}${mm}.pdf`;
      const opt: any = {
        margin:       10,
        filename,
        image:        { type: 'jpeg', quality: 0.95 },
        html2canvas:  { scale: 2, useCORS: true, logging: false },
        jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' }
      };
      // Clone the node and inline canvases from the live view as images
      const clone = answerRef.current.cloneNode(true) as HTMLElement;
      const liveCanvases = answerRef.current.querySelectorAll('canvas');
      const cloneCanvases = clone.querySelectorAll('canvas');
      const len = Math.min(liveCanvases.length, cloneCanvases.length);
      for (let i = 0; i < len; i++) {
        try {
          const live = liveCanvases[i] as HTMLCanvasElement;
          const url = live.toDataURL('image/png');
          const img = document.createElement('img');
          img.src = url;
          (img.style as any).width = '100%';
          (img.style as any).height = 'auto';
          const c = cloneCanvases[i];
          c.parentNode && c.parentNode.replaceChild(img, c);
        } catch {}
      }
      // Wrap with Q/A header
      const escapeHtml = (s: string) => String(s || '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'} as any)[ch] || ch);
      const qa = document.createElement('div');
      qa.innerHTML = `
        <div style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;">
          <div style="font-weight:700; font-size: 18px; margin-bottom:8px; text-align:left;">${escapeHtml(lastUserMessage)}</div>
        </div>
      `;
      qa.appendChild(clone);
      await (html2pdf() as any).set(opt).from(qa).save();
    } finally {
      setExporting(false);
    }
  }

  async function openPreview() {
    if (!answerRef.current) return;
    setPreviewLoading(true);
    try {
      // Build a clone with canvases inlined as images for preview
      const clone = answerRef.current.cloneNode(true) as HTMLElement;
      const liveCanvases = answerRef.current.querySelectorAll('canvas');
      const cloneCanvases = clone.querySelectorAll('canvas');
      const len = Math.min(liveCanvases.length, cloneCanvases.length);
      for (let i = 0; i < len; i++) {
        try {
          const live = liveCanvases[i] as HTMLCanvasElement;
          const url = live.toDataURL('image/png');
          const img = document.createElement('img');
          img.src = url;
          (img.style as any).width = '100%';
          (img.style as any).height = 'auto';
          const c = cloneCanvases[i];
          c.parentNode && c.parentNode.replaceChild(img, c);
        } catch {}
      }
      const escapeHtml = (s: string) => String(s || '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'} as any)[ch] || ch);
      const html = `
        <div style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;">
          <div style=\"font-weight:700; font-size: 18px; margin-bottom:8px; text-align:left;\">${escapeHtml(lastUserMessage)}</div>
          ${clone.innerHTML}
        </div>
      `;
      setPreviewHtml(html);
      setPreviewOpen(true);
    } finally {
      setPreviewLoading(false);
    }
  }

  function closePreview() {
    setPreviewOpen(false);
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
                            <Stack key={t.thread_id} direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
                              <Button
                                variant={t.thread_id === threadId ? 'contained' : 'text'}
                                size="small"
                                onClick={() => navigate(`/chat/${encodeURIComponent(t.thread_id)}`)}
                                sx={{ justifyContent: 'flex-start', textTransform: 'none', flex: 1, overflow: 'hidden' }}
                              >
                                <Typography noWrap maxWidth={180} variant="caption">{getThreadTitle(t)}</Typography>
                              </Button>
                              <IconButton size="small" color="error" onClick={() => deleteThreadById(t.thread_id)}>
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

                {/* Attached Files Context */}
                <AttachedFilesContext threadId={threadId} />

                {/* Messages / Streaming area */}
                {(lastUserMessage || draftAnswer || result || error || thoughts.length > 0 || tools.length > 0) ? (
                  <Box>
                    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

                    {/* User message bubble */}
                    {lastUserMessage && (
                      <Box sx={{ display: 'flex', mb: 2, minWidth: 0 }}>
                        <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, flex: 1, minWidth: 0, maxWidth: '100%', bgcolor: theme.palette.background.paper }}>
                          <Typography variant="subtitle2" sx={{ mb: 1.5 }}>You</Typography>
                          <Divider sx={{ mb: 1.5 }} />
                          <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                            {lastUserMessage}
                          </Typography>
                        </Paper>
                      </Box>
                    )}

                    {/* Assistant answer bubble (streams during generation, shows final when done) */}
                    {(draftAnswer || result?.answer) && (
                      <Box sx={{ display: 'flex', mb: 2, minWidth: 0 }}>
                        <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, flex: 1, minWidth: 0, maxWidth: '100%', bgcolor: theme.palette.background.paper }}>
                          <Typography variant="subtitle2" sx={{ mb: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
                            {loading && draftAnswer ? (
                              <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
                                <Box sx={(theme) => ({ width: 8, height: 8, borderRadius: '50%', background: `linear-gradient(135deg, ${theme.palette.primary.light}, ${theme.palette.primary.main})`, animation: `${bounce} 1.2s infinite ease-in-out`, animationDelay: '0s' })} />
                                <Box sx={(theme) => ({ width: 8, height: 8, borderRadius: '50%', background: `linear-gradient(135deg, ${theme.palette.primary.light}, ${theme.palette.primary.main})`, animation: `${bounce} 1.2s infinite ease-in-out`, animationDelay: '0.15s' })} />
                                <Box sx={(theme) => ({ width: 8, height: 8, borderRadius: '50%', background: `linear-gradient(135deg, ${theme.palette.primary.light}, ${theme.palette.primary.main})`, animation: `${bounce} 1.2s infinite ease-in-out`, animationDelay: '0.3s' })} />
                              </Box>
                            ) : (
                              'Answer'
                            )}
                          </Typography>
                          <Divider sx={{ mb: 1.5 }} />
                          {/* Removed top buttons per request */}
                          {/* Wrapper for export: includes answer text + charts */}
                          <Box ref={answerRef}>
                            <Box sx={{
                              overflowX: 'auto',
                              maxWidth: '100%',
                              wordBreak: 'break-word',
                              overflowWrap: 'anywhere',
                              WebkitOverflowScrolling: 'touch',
                              '& p': { m: 0 },
                              '& pre': { p: 1, borderRadius: 1, overflow: 'auto', maxWidth: '100%', bgcolor: theme.palette.mode === 'light' ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.06)' },
                              '& code': { whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
                              '& table': { display: 'block', width: 'max-content', maxWidth: 'none', minWidth: 640, borderCollapse: 'collapse', tableLayout: 'auto' },
                              '& th, & td': { border: `1px solid ${theme.palette.divider}`, padding: '4px 8px', verticalAlign: 'top', whiteSpace: 'nowrap', wordBreak: 'normal', overflowWrap: 'normal' },
                              '& img': { maxWidth: '100%', height: 'auto' }
                            }}>
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {draftAnswer || result?.answer || ''}
                              </ReactMarkdown>
                            </Box>

                            {/* Inline charts directly under answer text */}
                            {answerComplete && Array.isArray(result?.charts) && result!.charts!.length > 0 && (
                              <Box sx={{ mt: 2 }}>
                                <Stack spacing={2}>
                                  {result!.charts!.map((c, i) => (
                                    <Paper key={i} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                                      {c.title && <Typography variant="subtitle2" sx={{ mb: 1 }}>{c.title}</Typography>}
                                      {c && (c as any).spec && <ChartRenderer spec={(c as any).spec} onRendered={() => setChartsRendered(n => n + 1)} />}
                                    </Paper>
                                  ))}
                                </Stack>
                              </Box>
                            )}

                          </Box>
                          {/* Inline actions: like, dislike, export (left aligned). Not part of export content */}
                          {(result?.answer || draftAnswer) && (
                            <Box sx={{ mt: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                              <Tooltip title="Like">
                                <span>
                                  <IconButton size="small" disabled={loading}>
                                    <ThumbUpOffAlt fontSize="small" />
                                  </IconButton>
                                </span>
                              </Tooltip>
                              <Tooltip title="Dislike">
                                <span>
                                  <IconButton size="small" disabled={loading}>
                                    <ThumbDownOffAlt fontSize="small" />
                                  </IconButton>
                                </span>
                              </Tooltip>
                              <Tooltip title="Export PDF">
                                <span>
                                  <IconButton size="small" onClick={openPreview} disabled={previewLoading || exporting}>
                                    <IosShare fontSize="small" />
                                  </IconButton>
                                </span>
                              </Tooltip>
                              {(previewLoading || exporting) && (
                                <Typography variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
                                  {previewLoading ? 'Preparing…' : 'Exporting…'}
                                </Typography>
                              )}
                            </Box>
                          )}
                        </Paper>
                      </Box>
                    )}

                    {/* Details */}
                    {(result?.route || thoughts.length > 0 || tools.length > 0 || result?.data_preview) && (
                      <Paper variant="outlined" sx={{ p: 2, mb: 2, borderRadius: 3 }}>
                        <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                          <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <BoltRounded fontSize="small" color="primary" /> Details
                          </Typography>
                          <Box sx={{ flex: 1 }} />
                          <IconButton size="small" onClick={() => setDetailsOpen(v => !v)}>
                            {detailsOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                          </IconButton>
                        </Stack>
                        <Collapse in={detailsOpen}>
                          {result?.route && (
                            <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center" sx={{ mb: 1.5 }}>
                              {result.route.tool && <Chip size="small" label={`tool: ${result.route.tool}`} />}
                              {result.route.connector_type && <Chip size="small" label={`type: ${result.route.connector_type}`} />}
                              {result.route.connector_id && <Chip size="small" label={`connector: ${result.route.connector_id}`} />}
                            </Stack>
                          )}
                          {(thoughts.length > 0 || tools.length > 0) && (
                            <Box sx={{ mb: 1.5 }}>
                              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 0.5 }}>Agent Progress:</Typography>
                              {thoughts.map((t, i) => (
                                <Typography key={i} variant="body2" sx={{ color: 'text.secondary', mb: 0.5 }}>• {t}</Typography>
                              ))}
                              {tools.map((ev, i) => (
                                <Typography key={`tool-${i}`} variant="caption" sx={{ display: 'block', color: 'text.disabled' }}>
                                  [{ev.type === 'start' ? 'tool_start' : 'tool_end'}] {ev.tool}
                                </Typography>
                              ))}
                            </Box>
                          )}
                          {result?.data_preview && (
                            <TableContainer>
                              <Table size="small">
                                <TableHead>
                                  <TableRow>
                                    {result.data_preview.columns.map((col, i) => (
                                      <TableCell key={i}>{col}</TableCell>
                                    ))}
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  {result.data_preview.rows.map((row, i) => (
                                    <TableRow key={i}>
                                      {row.map((cell, j) => (
                                        <TableCell key={j}>{cell}</TableCell>
                                      ))}
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </TableContainer>
                          )}
                        </Collapse>
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

                {/* Input bar + bottom actions */}
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
                {/* Bottom actions removed per request */}
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
      <ChatPdfPreview
        open={previewOpen}
        html={previewHtml}
        onClose={closePreview}
        onExport={() => { closePreview(); setTimeout(() => exportPdf(), 0); }}
      />
    </Box>
  );
}

// Preview dialog at root to avoid clipping inside paper
// Note: We place it after component to keep file organization simple
export function ChatPdfPreview({ open, html, onClose, onExport }: { open: boolean; html: string; onClose: () => void; onExport: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Preview</DialogTitle>
      <DialogContent dividers>
        <Box sx={{ '& img': { maxWidth: '100%' } }} dangerouslySetInnerHTML={{ __html: html }} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button variant="contained" onClick={onExport}>Download PDF</Button>
      </DialogActions>
    </Dialog>
  );
}
