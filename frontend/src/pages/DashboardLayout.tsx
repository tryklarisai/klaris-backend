import React from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  AppBar,
  Toolbar,
  IconButton,
  Drawer,
  Box,
  List,
  ListItemButton,
  ListItemText,
  Divider,
  Button,
  Typography,
  Avatar,
  Tooltip,
  useMediaQuery,
  Breadcrumbs,
  Link as MuiLink,
  Collapse
} from "@mui/material";
import MenuIcon from '@mui/icons-material/Menu';
import DashboardIcon from '@mui/icons-material/Dashboard';
import ExtensionIcon from '@mui/icons-material/Extension';
import SchemaIcon from '@mui/icons-material/Hub';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';
import LogoutIcon from '@mui/icons-material/Logout';
import SettingsIcon from '@mui/icons-material/Settings';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import ChatIcon from '@mui/icons-material/Chat';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';
import AddRounded from '@mui/icons-material/AddRounded';
import { ModeContext } from "../theme/ThemeProvider";
import { SnackbarContext } from "../ui/SnackbarProvider";
import { getToken, isTokenExpired, clearAuthStorage } from "../utils/auth";
import { config, buildApiUrl } from "../config";

const drawerWidth = 260;

const mainMenu = [
  { key: "chat", label: "Chat", path: "/chat", icon: <ChatIcon fontSize="small" /> },
  { key: "dashboard", label: "Dashboard", path: "/dashboard", icon: <DashboardIcon fontSize="small" /> },
  { key: "connectors", label: "Connectors", path: "/connectors", icon: <ExtensionIcon fontSize="small" /> },
  { key: "relationships", label: "Data Relationships", path: "/relationships", icon: <SchemaIcon fontSize="small" /> },
  { key: "bcl", label: "Business Context", path: "/bcl", icon: <LibraryBooksIcon fontSize="small" /> },
  { key: "usage", label: "Usage", path: "/usage", icon: <SchemaIcon fontSize="small" /> }
];

type ThreadItem = { thread_id: string; title?: string | null };

export default function DashboardLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeKey = React.useMemo(() => {
    const p = location.pathname || '';
    if (p === '/' || p.startsWith('/chat')) return 'chat';
    if (p.startsWith('/dashboard')) return 'dashboard';
    if (p.startsWith('/connectors')) return 'connectors';
    if (p.startsWith('/relationships')) return 'relationships';
    if (p.startsWith('/usage')) return 'usage';
    if (p.startsWith('/bcl')) return 'bcl';
    if (p.startsWith('/profile')) return 'profile';
    return 'chat';
  }, [location.pathname]);
  const isMobile = useMediaQuery('(max-width:900px)');
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const { mode, toggleMode } = React.useContext(ModeContext);
  const { notify } = React.useContext(SnackbarContext);

  const [chatExpanded, setChatExpanded] = React.useState(true);
  const [threads, setThreads] = React.useState<ThreadItem[]>([]);
  const [threadsLoading, setThreadsLoading] = React.useState(false);
  const threadsFetchSeq = React.useRef(0);
  const currentThreadId = location.pathname.startsWith('/chat/')
    ? decodeURIComponent(location.pathname.slice('/chat/'.length))
    : null;

  const getThreadTitle = React.useCallback((t: ThreadItem) => {
    const title = (t.title ? String(t.title) : '').trim();
    return title || `Thread - ${t.thread_id.slice(0, 8)}`;
  }, []);

  const handleLogout = () => {
    window.localStorage.removeItem("klaris_jwt");
    window.localStorage.removeItem("klaris_user");
    window.localStorage.removeItem("klaris_tenant");
    navigate("/login");
  };

  const fetchThreads = React.useCallback(async () => {
    const seq = ++threadsFetchSeq.current;
    setThreadsLoading(true);
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      if (!token) { if (seq === threadsFetchSeq.current) setThreads([]); return; }
      const resp = await fetch(buildApiUrl('/api/v1/chat/threads'), {
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
      if (seq === threadsFetchSeq.current) setThreads(list);
    } finally {
      if (seq === threadsFetchSeq.current) setThreadsLoading(false);
    }
  }, []);

  React.useEffect(() => { fetchThreads(); }, [fetchThreads]);

  // Auth guard: check token on route change and on mount
  React.useEffect(() => {
    const token = getToken();
    if (!token || isTokenExpired(token)) {
      clearAuthStorage();
      notify('Your session has expired. Please login again.', 'warning');
      navigate('/login', { replace: true });
    }
    // Also set up periodic check (every 60s)
    const id = window.setInterval(() => {
      const t = getToken();
      if (!t || isTokenExpired(t)) {
        clearAuthStorage();
        notify('Your session has expired. Please login again.', 'warning');
        navigate('/login', { replace: true });
      }
    }, 60000);
    return () => window.clearInterval(id);
  }, [location.pathname, navigate, notify]);

  // Refresh threads in sidebar when ChatPage creates/deletes threads
  React.useEffect(() => {
    const onChanged = (ev: Event) => {
      fetchThreads();
    };
    window.addEventListener('chat:threads:changed', onChanged as any);
    return () => window.removeEventListener('chat:threads:changed', onChanged as any);
  }, [fetchThreads]);

  async function handleCreateThread() {
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      if (!token) { return; }
      const resp = await fetch(buildApiUrl('/api/v1/chat/threads'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) return;
      const data = await resp.json();
      const tid = String(data?.thread_id || '');
      if (tid) {
        navigate(`/chat/${encodeURIComponent(tid)}`);
        setMobileOpen(false);
      }
      await fetchThreads();
    } catch {
      // ignore
    }
  }

  async function deleteThreadById(id: string) {
    try {
      const token = window.localStorage.getItem('klaris_jwt');
      if (!token) { return; }
      const resp = await fetch(buildApiUrl(`/api/v1/chat/threads/${encodeURIComponent(id)}`), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) return;
      if (currentThreadId === id) {
        navigate('/chat');
      }
      await fetchThreads();
    } catch {
      // ignore
    }
  }

  const drawer = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Spacer to avoid AppBar overlap (two toolbars in AppBar) */}
      <Toolbar />
      <Toolbar />
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 2 }}>
        <Avatar src={config.logoUrl} sx={{ width: 28, height: 28 }} />
        <Typography variant="h6" noWrap>{config.brandName}</Typography>
      </Box>
      <Divider />
      <List sx={{ flex: 1 }}>
        {mainMenu.map(item => (
          item.key !== 'chat' ? (
            <ListItemButton
              key={item.key}
              selected={activeKey === item.key}
              onClick={() => {
                navigate(item.path);
                setMobileOpen(false);
              }}
            >
              {item.icon}
              <ListItemText primary={item.label} sx={{ ml: 1.5 }} />
            </ListItemButton>
          ) : (
            <React.Fragment key={item.key}>
              <ListItemButton
                selected={activeKey === 'chat'}
                onClick={() => {
                  navigate(item.path);
                  setMobileOpen(false);
                }}
              >
                {item.icon}
                <ListItemText primary={item.label} sx={{ ml: 1.5 }} />
                <IconButton size="small" onClick={(e) => { e.stopPropagation(); setChatExpanded(v => !v); }}>
                  {chatExpanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                </IconButton>
              </ListItemButton>
              <Collapse in={chatExpanded} timeout="auto" unmountOnExit>
                <Box sx={{ pl: 5, pr: 1, py: 1 }}>
                  <Button startIcon={<AddRounded />} size="small" variant="outlined" onClick={handleCreateThread} disabled={threadsLoading}>
                    New thread
                  </Button>
                  <Box sx={{ mt: 1 }}>
                    {threadsLoading ? (
                      <Typography variant="caption" color="text.secondary">Loading…</Typography>
                    ) : threads.length === 0 ? (
                      <Typography variant="caption" color="text.secondary">No threads</Typography>
                    ) : (
                      threads.map((t) => (
                        <Box key={t.thread_id} sx={{ display: 'flex', alignItems: 'center' }}>
                          <ListItemButton
                            selected={currentThreadId === t.thread_id}
                            onClick={() => { navigate(`/chat/${encodeURIComponent(t.thread_id)}`); setMobileOpen(false); }}
                            sx={{ borderRadius: 1 }}
                          >
                            <ListItemText primaryTypographyProps={{ noWrap: true }} primary={getThreadTitle(t)} />
                          </ListItemButton>
                          <IconButton size="small" color="error" onClick={() => deleteThreadById(t.thread_id)}>
                            <DeleteOutlineRounded fontSize="small" />
                          </IconButton>
                        </Box>
                      ))
                    )}
                  </Box>
                </Box>
              </Collapse>
            </React.Fragment>
          )
        ))}
        <ListItemButton
          key={'profile'}
          selected={activeKey === 'profile'}
          onClick={() => { navigate('/profile'); setMobileOpen(false); }}
        >
          <SettingsIcon fontSize="small" />
          <ListItemText primary={'Profile'} sx={{ ml: 1.5 }} />
        </ListItemButton>
      </List>
      <Divider />
      <Box sx={{ p: 2 }}>
        <Button startIcon={<LogoutIcon />} variant="outlined" color="warning" fullWidth size="small" onClick={handleLogout}>Logout</Button>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex' }}>
      <AppBar position="fixed" color="inherit" sx={{ zIndex: theme => theme.zIndex.drawer + 1 }}>
        <Toolbar>
          {isMobile && (
            <IconButton edge="start" onClick={() => setMobileOpen(true)}>
              <MenuIcon />
            </IconButton>
          )}
          {!isMobile && (
            <Typography variant="h6" sx={{ mr: 2 }}>{config.brandName}</Typography>
          )}
          <Box sx={{ flex: 1 }} />
          <Tooltip title={`Toggle ${mode === 'light' ? 'dark' : 'light'} mode`}>
            <IconButton onClick={toggleMode}>
              {mode === 'light' ? <Brightness4Icon /> : <Brightness7Icon />}
            </IconButton>
          </Tooltip>
        </Toolbar>
        <Toolbar sx={{ px: 3 }}>
          <Breadcrumbs aria-label="breadcrumb">
            <MuiLink color="inherit" onClick={() => navigate('/')} underline="hover" sx={{ cursor: 'pointer' }}>Home</MuiLink>
            {activeKey !== 'chat' && <Typography color="text.primary">{activeKey}</Typography>}
          </Breadcrumbs>
        </Toolbar>
      </AppBar>

      {/* Side navigation */}
      {isMobile ? (
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{ [`& .MuiDrawer-paper`]: { width: drawerWidth } }}
        >
          {drawer}
        </Drawer>
      ) : (
        <Drawer variant="permanent" sx={{ [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box' } }}>
          {drawer}
        </Drawer>
      )}

      <Box component="main" sx={{ flexGrow: 1, ml: { md: `${drawerWidth}px` }, width: '100%', px: 3, pt: 16, pb: 4 }}>
        <Outlet />
      </Box>
    </Box>
  );
}