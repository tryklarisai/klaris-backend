import React, { useEffect, useMemo, useState } from 'react';
import { buildApiUrl } from '../config';
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { Box, FormControl, InputLabel, MenuItem, Select, SelectChangeEvent, Typography } from '@mui/material';

function useAuthHeaders() {
  return React.useMemo(() => {
    const token = localStorage.getItem('klaris_jwt') || '';
    const tenantJson = localStorage.getItem('klaris_tenant');
    const tenant = tenantJson ? JSON.parse(tenantJson) : null;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (tenant?.tenant_id) headers['X-Tenant-ID'] = tenant.tenant_id;
    return headers;
  }, []);
}

function computeFromISO(range: string, now: Date): string | null {
  const ms = {
    '15m': 15 * 60 * 1000,
    '1h': 1 * 60 * 60 * 1000,
    '4h': 4 * 60 * 60 * 1000,
    '24h': 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
  } as const;
  const delta = (ms as any)[range] ?? ms['24h'];
  const from = new Date(now.getTime() - delta);
  return from.toISOString();
}

export default function UsagePage() {
  const headers = useAuthHeaders();
  const [series, setSeries] = useState<any[]>([]);
  const [summary, setSummary] = useState<any | null>(null);
  const [range, setRange] = useState<string>("24h");
  const tenant = useMemo(() => {
    const t = localStorage.getItem('klaris_tenant');
    return t ? JSON.parse(t) : null;
  }, []);

  useEffect(() => {
    async function load() {
      if (!tenant?.tenant_id) return;
      const qs = new URLSearchParams();
      const now = new Date();
      const to = now.toISOString();
      const from = computeFromISO(range, now);
      if (from) qs.set('from', from);
      qs.set('to', to);
      // No additional filters; show overall usage for range
      const sres = await fetch(buildApiUrl(`/api/v1/usage/${tenant.tenant_id}/series?` + qs.toString()), { headers } as RequestInit);
      const sjson = await sres.json();
      const points = (sjson.series || []).map((p: any) => ({
        hour: new Date(p.hour).toLocaleString(),
        total: Number(p.total_tokens || 0),
        input: Number(p.input_tokens || 0),
        output: Number(p.output_tokens || 0),
      }));
      setSeries(points);
      const sumres = await fetch(buildApiUrl(`/api/v1/usage/${tenant.tenant_id}/summary?` + qs.toString()), { headers } as RequestInit);
      const sumjson = await sumres.json();
      setSummary(sumjson || null);
    }
    load();
  }, [headers, tenant, range]);

  const catData = useMemo(() => (summary?.by_category || []).map((r: any) => ({ name: r.category || 'uncategorized', input: Number(r.input_tokens || 0), output: Number(r.output_tokens || 0) })), [summary]);
  const modelData = useMemo(() => (summary?.by_model || []).map((r: any) => ({ name: r.model || 'unknown', input: Number(r.input_tokens || 0), output: Number(r.output_tokens || 0) })), [summary]);
  const byModule = useMemo(() => (summary?.by_module || []).map((r: any) => ({ name: r.module || 'unknown', input: Number(r.input_tokens || 0), output: Number(r.output_tokens || 0) })), [summary]);

  return (
    <div style={{ padding: 24 }}>
      <Typography variant="h5" component="h2">Usage</Typography>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap', mt: 1 }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel id="usage-range-label">Time Range</InputLabel>
          <Select
            labelId="usage-range-label"
            id="usage-range"
            value={range}
            label="Time Range"
            onChange={(e: SelectChangeEvent) => setRange(String(e.target.value))}
          >
            <MenuItem value="15m">Last 15 mins</MenuItem>
            <MenuItem value="1h">Last 1 hour</MenuItem>
            <MenuItem value="4h">Last 4 hours</MenuItem>
            <MenuItem value="24h">Last 24 hours</MenuItem>
            <MenuItem value="7d">Last 7 days</MenuItem>
          </Select>
        </FormControl>
      </Box>
      <div style={{ marginTop: 16 }}>
        <Typography variant="subtitle1" sx={{ mb: 1 }}>Tokens per hour</Typography>
        {series.length === 0 ? (
          <div style={{ fontSize: 12, color: '#666' }}>No usage recorded.</div>
        ) : (
          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={series} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="hour" tick={{ fontSize: 10 }} interval={series.length > 12 ? Math.ceil(series.length / 12) : 0} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="total" stroke="#5e35b1" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="input" stroke="#42a5f5" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="output" stroke="#ffb74d" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
      <div style={{ marginTop: 24 }}>
        <Typography variant="subtitle1" sx={{ mb: 1 }}>Summary</Typography>
        {summary && (
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <div style={{ minWidth: 360, flex: '1 1 360px', height: 280 }}>
              <Typography sx={{ fontWeight: 600, mb: 1 }}>By Category</Typography>
              <ResponsiveContainer>
                <BarChart data={catData} layout="vertical" margin={{ top: 10, right: 20, left: 20, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="input" stackId="a" fill="#42a5f5" radius={4} />
                  <Bar dataKey="output" stackId="a" fill="#ffb74d" radius={4} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div style={{ minWidth: 360, flex: '1 1 360px', height: 280 }}>
              <Typography sx={{ fontWeight: 600, mb: 1 }}>By Module</Typography>
              <ResponsiveContainer>
                <BarChart data={byModule} layout="vertical" margin={{ top: 10, right: 20, left: 20, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="input" stackId="a" fill="#42a5f5" radius={4} />
                  <Bar dataKey="output" stackId="a" fill="#ffb74d" radius={4} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div style={{ minWidth: 360, flex: '1 1 360px', height: 280 }}>
              <Typography sx={{ fontWeight: 600, mb: 1 }}>By Model</Typography>
              <ResponsiveContainer>
                <BarChart data={modelData} layout="vertical" margin={{ top: 10, right: 20, left: 20, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="input" stackId="a" fill="#42a5f5" radius={4} />
                  <Bar dataKey="output" stackId="a" fill="#ffb74d" radius={4} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


