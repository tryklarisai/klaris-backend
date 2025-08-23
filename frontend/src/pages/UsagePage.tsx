import React, { useEffect, useMemo, useState } from 'react';
import { buildApiUrl } from '../config';
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer, BarChart, Bar } from 'recharts';

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

export default function UsagePage() {
  const headers = useAuthHeaders();
  const [series, setSeries] = useState<any[]>([]);
  const [summary, setSummary] = useState<any | null>(null);
  const tenant = useMemo(() => {
    const t = localStorage.getItem('klaris_tenant');
    return t ? JSON.parse(t) : null;
  }, []);

  useEffect(() => {
    async function load() {
      if (!tenant?.tenant_id) return;
      const qs = new URLSearchParams();
      const now = new Date();
      const from = new Date(now.getTime() - 24 * 3600 * 1000).toISOString();
      const to = now.toISOString();
      qs.set('from', from);
      qs.set('to', to);
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
  }, [headers, tenant]);

  const catData = useMemo(() => (summary?.by_category || []).map((r: any) => ({ name: r.category || 'uncategorized', tokens: Number(r.total_tokens || 0) })), [summary]);
  const modelData = useMemo(() => (summary?.by_model || []).map((r: any) => ({ name: r.model || 'unknown', tokens: Number(r.total_tokens || 0) })), [summary]);

  return (
    <div style={{ padding: 24 }}>
      <h2>Usage</h2>
      <div style={{ marginTop: 16 }}>
        <h3>Tokens per hour (last 24h)</h3>
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
                <Line type="monotone" dataKey="total" stroke="#1976d2" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="input" stroke="#2e7d32" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="output" stroke="#ef6c00" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
      <div style={{ marginTop: 24 }}>
        <h3>Summary (last 24h)</h3>
        {summary && (
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <div style={{ minWidth: 360, flex: '1 1 360px', height: 280 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>By Category</div>
              <ResponsiveContainer>
                <BarChart data={catData} layout="vertical" margin={{ top: 10, right: 20, left: 20, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="tokens" fill="#1976d2" radius={4} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div style={{ minWidth: 360, flex: '1 1 360px', height: 280 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>By Model</div>
              <ResponsiveContainer>
                <BarChart data={modelData} layout="vertical" margin={{ top: 10, right: 20, left: 20, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="tokens" fill="#7b68ee" radius={4} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


