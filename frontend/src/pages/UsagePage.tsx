import React, { useEffect, useMemo, useState } from 'react';
import { buildApiUrl } from '../config';

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
    const t = localStorage.getItem('tenant');
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
      setSeries(sjson.series || []);
      const sumres = await fetch(buildApiUrl(`/api/v1/usage/${tenant.tenant_id}/summary?` + qs.toString()), { headers } as RequestInit);
      const sumjson = await sumres.json();
      setSummary(sumjson || null);
    }
    load();
  }, [headers, tenant]);

  return (
    <div style={{ padding: 24 }}>
      <h2>Usage</h2>
      <div style={{ marginTop: 16 }}>
        <h3>Tokens per hour (last 24h)</h3>
        <div style={{ fontSize: 12, color: '#666' }}>
          {series.map((p: any) => (
            <div key={p.hour}>
              <strong>{new Date(p.hour).toLocaleString()}</strong>: total={p.total_tokens} (in={p.input_tokens}, out={p.output_tokens})
            </div>
          ))}
          {series.length === 0 && <div>No usage recorded.</div>}
        </div>
      </div>
      <div style={{ marginTop: 24 }}>
        <h3>Summary (last 24h)</h3>
        {summary && (
          <div style={{ fontSize: 12, color: '#666' }}>
            <div>Total tokens: {summary.total?.total_tokens}</div>
            <div style={{ marginTop: 8 }}><strong>By Category</strong></div>
            {(summary.by_category || []).map((r: any) => (
              <div key={r.category || 'uncategorized'}>{r.category || 'uncategorized'}: {r.total_tokens}</div>
            ))}
            <div style={{ marginTop: 8 }}><strong>By Model</strong></div>
            {(summary.by_model || []).map((r: any) => (
              <div key={r.model || 'unknown'}>{r.model || 'unknown'}: {r.total_tokens}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


