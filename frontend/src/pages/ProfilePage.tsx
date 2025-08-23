import React from "react";
import { Box, Typography, Tabs, Tab, Stack, TextField, Button, Paper, Alert } from "@mui/material";
import { buildApiUrl } from "../config";

function useAuthHeaders() {
  return React.useMemo(() => {
    const token = window.localStorage.getItem("klaris_jwt");
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
  }, []);
}

export default function ProfilePage() {
  const [tab, setTab] = React.useState(0);
  return (
    <Box sx={{ mt: 7 }}>
      <Typography variant="h4" sx={{ mb: 1 }}>Profile</Typography>
      <Paper sx={{ mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label="Config Settings" />
        </Tabs>
      </Paper>
      {tab === 0 && <ConfigSettings />}
    </Box>
  );
}

function ConfigSettings() {
  const headers = useAuthHeaders();
  const [tenantId, setTenantId] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [savedMsg, setSavedMsg] = React.useState<string | null>(null);
  const [settings, setSettings] = React.useState<Record<string, any>>({});

  React.useEffect(() => {
    const tStr = window.localStorage.getItem('klaris_tenant');
    if (tStr) {
      try {
        const t = JSON.parse(tStr);
        setTenantId(t.tenant_id);
      } catch {}
    }
  }, []);

  const load = React.useCallback(async () => {
    if (!tenantId) return;
    setLoading(true); setError(null); setSavedMsg(null);
    try {
      const resp = await fetch(buildApiUrl(`/api/v1/tenants/${tenantId}/settings`), { headers } as RequestInit);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || 'Failed to load settings');
      setSettings(data?.settings || {});
    } catch (e: any) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [tenantId, headers]);

  React.useEffect(() => { load(); }, [load]);

  const fields: Array<{ key: string; label: string; type?: string }> = [
    { key: 'LLM_PROVIDER', label: 'LLM Provider' },
    { key: 'LLM_MODEL', label: 'LLM Model' },
    { key: 'LLM_TEMPERATURE', label: 'LLM Temperature', type: 'number' },
    { key: 'LLM_API_KEY', label: 'LLM API Key' },
    { key: 'OPENAI_BASE_URL', label: 'OpenAI Base URL' },
    { key: 'CHAT_HISTORY_MAX_TURNS', label: 'Chat History Max Turns', type: 'number' },
    { key: 'EMBEDDING_PROVIDER', label: 'Embedding Provider' },
    { key: 'EMBEDDING_MODEL', label: 'Embedding Model' },
    { key: 'EMBEDDING_API_KEY', label: 'Embedding API Key' },
  ];

  async function save() {
    if (!tenantId) return;
    setSaving(true); setError(null); setSavedMsg(null);
    try {
      const resp = await fetch(buildApiUrl(`/api/v1/tenants/${tenantId}/settings`), {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings }),
      } as RequestInit);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || 'Failed to save settings');
      setSavedMsg('Settings saved');
    } catch (e: any) {
      setError(e.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Paper sx={{ p: 2 }}>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {savedMsg && <Alert severity="success" sx={{ mb: 2 }}>{savedMsg}</Alert>}
      <Stack spacing={2}>
        {fields.map(f => (
          <TextField
            key={f.key}
            label={f.label}
            type={f.type || 'text'}
            value={settings[f.key] ?? ''}
            onChange={(e) => setSettings(s => ({ ...s, [f.key]: f.type === 'number' ? Number(e.target.value) : e.target.value }))}
            fullWidth
            size="small"
          />
        ))}
        <Stack direction="row" spacing={1}>
          <Button variant="contained" onClick={save} disabled={saving || loading}>Save</Button>
          <Button variant="text" onClick={load} disabled={loading}>Reload</Button>
        </Stack>
      </Stack>
    </Paper>
  );
}


