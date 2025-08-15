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
  Link as MuiLink
} from "@mui/material";
import MenuIcon from '@mui/icons-material/Menu';
import DashboardIcon from '@mui/icons-material/Dashboard';
import ExtensionIcon from '@mui/icons-material/Extension';
import SchemaIcon from '@mui/icons-material/Hub';
import WorkIcon from '@mui/icons-material/WorkOutline';
import LogoutIcon from '@mui/icons-material/Logout';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import { ModeContext } from "../theme/ThemeProvider";
import { config } from "../config";

const drawerWidth = 260;

const mainMenu = [
  { key: "dashboard", label: "Dashboard", path: "/", icon: <DashboardIcon fontSize="small" /> },
  { key: "connectors", label: "Connectors", path: "/connectors", icon: <ExtensionIcon fontSize="small" /> },
  { key: "relationships", label: "Data Relationships", path: "/relationships", icon: <SchemaIcon fontSize="small" /> },
  { key: "business-context", label: "Business Context", path: "/business-context", icon: <WorkIcon fontSize="small" /> }
];

export default function DashboardLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeKey = mainMenu.find(item => item.path === location.pathname)?.key || "dashboard";
  const isMobile = useMediaQuery('(max-width:900px)');
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const { mode, toggleMode } = React.useContext(ModeContext);

  const handleLogout = () => {
    window.localStorage.removeItem("klaris_jwt");
    window.localStorage.removeItem("klaris_user");
    window.localStorage.removeItem("klaris_tenant");
    navigate("/login");
  };

  const drawer = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 2 }}>
        <Avatar src={config.logoUrl} sx={{ width: 28, height: 28 }} />
        <Typography variant="h6" noWrap>{config.brandName}</Typography>
      </Box>
      <Divider />
      <List sx={{ flex: 1 }}>
        {mainMenu.map(item => (
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
        ))}
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
            {activeKey !== 'dashboard' && <Typography color="text.primary">{activeKey}</Typography>}
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