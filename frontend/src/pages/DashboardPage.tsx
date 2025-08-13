import React, { useEffect, useState } from "react";
import { Card, CardContent, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";

/**
 * DashboardPage
 * Thin welcome/info page for after login, used inside DashboardLayout sidebar shell.
 * All sidebar, navigation, and tenants/connectors content now lives in the layout/pages, not here.
 */
export default function DashboardPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<any>(null);
  const [tenant, setTenant] = useState<any>(null);

  useEffect(() => {
    const userStr = window.localStorage.getItem("klaris_user");
    const tStr = window.localStorage.getItem("klaris_tenant");
    const jwt = window.localStorage.getItem("klaris_jwt");
    if (!userStr || !tStr || !jwt) {
      navigate("/login", { replace: true });
      return;
    }
    setUser(JSON.parse(userStr));
    setTenant(JSON.parse(tStr));
  }, [navigate]);

  return (
    <Card>
      <CardContent>
        <Typography variant="h5" mb={1}>Welcome{user?.name ? ", " + user.name : ""}</Typography>
        <Typography variant="subtitle1" mb={1}>
          Tenant: <b>{tenant?.name || "-"}</b> (plan: <b>{tenant?.plan || "-"}</b>)
        </Typography>
        <Typography variant="body2" color="text.secondary" mt={2}>
          Use the menu to manage tenants, connectors, onboarding, and usage analytics.
        </Typography>
      </CardContent>
    </Card>
  );
}
