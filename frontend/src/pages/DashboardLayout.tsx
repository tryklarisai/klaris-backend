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
import ChatIcon from '@mui/icons-material/Chat';
import { ModeContext } from "../theme/ThemeProvider";
import { config } from "../config";

const drawerWidth = 280;

const mainMenu = [
  { key: "connectors", label: "Connectors", path: "/connectors", icon: <ExtensionIcon fontSize="small" /> },
  { key: "relationships", label: "Data Relationships", path: "/relationships", icon: <SchemaIcon fontSize="small" /> },
  { key: "business-context", label: "Business Context", path: "/business-context", icon: <WorkIcon fontSize="small" /> },
  { key: "chat", label: "Chat", path: "/chat", icon: <ChatIcon fontSize="small" /> }
];

export default function DashboardLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeKey = mainMenu.find(item => item.path === location.pathname)?.key || "connectors";
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
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', bgcolor: 'background.paper' }}>
      <Box sx={{ p: 3, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Avatar src={config.logoUrl} sx={{ width: 32, height: 32 }} />
          <Typography variant="h5" fontWeight={700} color="primary">{config.brandName}</Typography>
        </Box>
      </Box>
      <List sx={{ flex: 1, px: 2, py: 3 }}>
        {mainMenu.map(item => (
          <ListItemButton
            key={item.key}
            selected={activeKey === item.key}
            onClick={() => {
              navigate(item.path);
              setMobileOpen(false);
            }}
            sx={{
              borderRadius: 2,
              mb: 1,
              '&.Mui-selected': {
                bgcolor: 'primary.main',
                color: 'primary.contrastText',
                '&:hover': {
                  bgcolor: 'primary.dark',
                },
              },
              '&:hover': {
                bgcolor: 'action.hover',
              },
            }}
          >
            <Box sx={{ mr: 2, display: 'flex', alignItems: 'center', color: 'inherit' }}>
              {item.icon}
            </Box>
            <ListItemText 
              primary={item.label} 
              primaryTypographyProps={{
                fontWeight: activeKey === item.key ? 600 : 500,
                fontSize: '0.95rem'
              }}
            />
          </ListItemButton>
        ))}
      </List>
      <Box sx={{ p: 3, borderTop: '1px solid', borderColor: 'divider' }}>
        <Box sx={{ mb: 2 }}>
          <Tooltip title={`Toggle ${mode === 'light' ? 'dark' : 'light'} mode`}>
            <IconButton onClick={toggleMode} size="small" sx={{ mr: 1 }}>
              {mode === 'light' ? <Brightness4Icon fontSize="small" /> : <Brightness7Icon fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Box>
        <Button 
          startIcon={<LogoutIcon />} 
          variant="outlined" 
          color="error" 
          fullWidth 
          size="medium" 
          onClick={handleLogout}
        >
          Logout
        </Button>
      </Box>
    </Box>
  );

  // Get page title and description based on current path
  const getPageInfo = () => {
    const currentItem = mainMenu.find(item => item.path === location.pathname);
    if (currentItem) {
      switch (currentItem.key) {
        case 'connectors':
          return { title: 'Configure Connectors', description: 'Manage your data source connections' };
        case 'relationships':
          return { title: 'Define Data Relationships', description: 'Map connections between your data sources' };
        case 'business-context':
          return { title: 'Business Context', description: 'Add business meaning to your data' };
        case 'chat':
          return { title: 'Chat', description: 'Interact with your data using natural language' };
        default:
          return { title: currentItem.label, description: '' };
      }
    }
    // Handle connector detail pages
    if (location.pathname.includes('/connectors/')) {
      return { title: 'Connector Details', description: 'Configure and manage your connector' };
    }
    return { title: 'Dashboard', description: 'Welcome to Klaris' };
  };

  const pageInfo = getPageInfo();

  return (
    <Box sx={{ display: 'flex', height: '100vh' }}>
      {/* Side navigation */}
      {isMobile ? (
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{ 
            [`& .MuiDrawer-paper`]: { 
              width: drawerWidth,
              boxSizing: 'border-box'
            } 
          }}
        >
          {drawer}
        </Drawer>
      ) : (
        <Drawer 
          variant="permanent" 
          sx={{ 
            [`& .MuiDrawer-paper`]: { 
              width: drawerWidth, 
              boxSizing: 'border-box',
              borderRight: '1px solid',
              borderColor: 'divider'
            } 
          }}
        >
          {drawer}
        </Drawer>
      )}

      {/* Main content area */}
      <Box component="main" sx={{ 
        flexGrow: 1, 
        ml: { xs: 0, md: `${drawerWidth}px` }, 
        width: { xs: '100%', md: `calc(100% - ${drawerWidth}px)` },
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        overflow: 'hidden'
      }}>
        {/* Mobile menu button and page header */}
        <Box sx={{ 
          p: 3, 
          borderBottom: '1px solid', 
          borderColor: 'divider',
          bgcolor: 'background.paper',
          flexShrink: 0
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              {isMobile && (
                <IconButton 
                  edge="start" 
                  onClick={() => setMobileOpen(true)}
                  sx={{ mr: 1 }}
                >
                  <MenuIcon />
                </IconButton>
              )}
              <Box>
                <Typography variant="h5" fontWeight={600} sx={{ mb: 0.5 }}>
                  {pageInfo.title}
                </Typography>
                {pageInfo.description && (
                  <Typography variant="body2" color="text.secondary">
                    {pageInfo.description}
                  </Typography>
                )}
              </Box>
            </Box>
            {isMobile && (
              <Tooltip title={`Toggle ${mode === 'light' ? 'dark' : 'light'} mode`}>
                <IconButton onClick={toggleMode}>
                  {mode === 'light' ? <Brightness4Icon /> : <Brightness7Icon />}
                </IconButton>
              </Tooltip>
            )}
          </Box>
        </Box>

        {/* Page content */}
        <Box sx={{ 
          flex: 1,
          overflow: 'auto',
          p: 3
        }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}