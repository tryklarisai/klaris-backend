import React from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Drawer, Box, List, ListItemButton, ListItemText, Divider, Button, Typography } from "@mui/material";

const drawerWidth = 260;

const mainMenu = [
  { key: "dashboard", label: "Dashboard", path: "/" },
  { key: "connectors", label: "Connectors", path: "/connectors" }
];

export default function DashboardLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeKey = mainMenu.find(item => item.path === location.pathname)?.key || "dashboard";

  const handleLogout = () => {
    window.localStorage.removeItem("klaris_jwt");
    window.localStorage.removeItem("klaris_user");
    window.localStorage.removeItem("klaris_tenant");
    navigate("/login");
  };

  return (
    <Box sx={{ display: "flex" }}>
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: {
            width: drawerWidth,
            boxSizing: "border-box",
            zIndex: 1000,
          },
        }}
      >
        <Box sx={{ mt: 6, mb: 2, px: 2 }}>
          <Typography variant="h5">Menu</Typography>
        </Box>
        <Divider />
        <List>
          {mainMenu.map(item => (
            <ListItemButton
              key={item.key}
              selected={activeKey === item.key}
              onClick={() => navigate(item.path)}
            >
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
        </List>
        <Divider />
        <Box sx={{ p: 2, mt: 2 }}>
          <Button variant="outlined" color="warning" fullWidth size="small" onClick={handleLogout}>Logout</Button>
        </Box>
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, ml: `${drawerWidth}px`, mt: 8, px: 2, width: "100%" }}>
        <Outlet />
      </Box>
    </Box>
  );
}