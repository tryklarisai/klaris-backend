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
        {series.length === 0 ? (
          <div style={{ fontSize: 12, color: '#666' }}>No usage recorded.</div>
        ) : (
          <LineTokensChart points={series} width={720} height={220} />
        )}
      </div>
      <div style={{ marginTop: 24 }}>
        <h3>Summary (last 24h)</h3>
        {summary && (
          <div>
            <div style={{ fontSize: 13, color: '#444', marginBottom: 6 }}>Total tokens: {summary.total?.total_tokens}</div>
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
              <div style={{ minWidth: 320, flex: '1 1 320px' }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>By Category</div>
                <Bars tokens={(summary.by_category || []).map((r: any) => ({ label: r.category || 'uncategorized', value: Number(r.total_tokens || 0) }))} />
              </div>
              <div style={{ minWidth: 320, flex: '1 1 320px' }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>By Model</div>
                <Bars tokens={(summary.by_model || []).map((r: any) => ({ label: r.model || 'unknown', value: Number(r.total_tokens || 0) }))} color="#7b68ee" />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function LineTokensChart({ points, width, height }: { points: any[]; width: number; height: number }) {
  const pad = { top: 16, right: 16, bottom: 28, left: 40 };
  const w = Math.max(200, width);
  const h = Math.max(140, height);
  const xs = points.map((p) => new Date(p.hour).getTime());
  const ysTotal = points.map((p) => Number(p.total_tokens || 0));
  const ysIn = points.map((p) => Number(p.input_tokens || 0));
  const ysOut = points.map((p) => Number(p.output_tokens || 0));
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMax = Math.max(1, Math.max(...ysTotal, ...ysIn, ...ysOut));
  const xScale = (x: number) => pad.left + ((x - xMin) / Math.max(1, xMax - xMin)) * (w - pad.left - pad.right);
  const yScale = (y: number) => h - pad.bottom - (y / yMax) * (h - pad.top - pad.bottom);
  const path = (ys: number[]) => ys.map((y, i) => `${i === 0 ? 'M' : 'L'} ${xScale(xs[i]).toFixed(1)} ${yScale(y).toFixed(1)}`).join(' ');
  const ticks = 4;
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => Math.round((yMax * i) / ticks));
  const fmt = (v: number) => v.toLocaleString();
  return (
    <svg width={w} height={h} role="img" aria-label="Tokens per hour">
      <rect x={0} y={0} width={w} height={h} fill="#fff" />
      {/* Axes */}
      <line x1={pad.left} y1={h - pad.bottom} x2={w - pad.right} y2={h - pad.bottom} stroke="#ccc" />
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={h - pad.bottom} stroke="#ccc" />
      {yTicks.map((t, i) => (
        <g key={i}>
          <line x1={pad.left} y1={yScale(t)} x2={w - pad.right} y2={yScale(t)} stroke="#f0f0f0" />
          <text x={pad.left - 8} y={yScale(t)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="#666">{fmt(t)}</text>
        </g>
      ))}
      {/* Lines */}
      <path d={path(ysTotal)} fill="none" stroke="#1976d2" strokeWidth={2} />
      <path d={path(ysIn)} fill="none" stroke="#2e7d32" strokeWidth={1.5} />
      <path d={path(ysOut)} fill="none" stroke="#ef6c00" strokeWidth={1.5} />
      {/* Legend */}
      <g transform={`translate(${pad.left}, ${pad.top - 6})`}>
        <LegendItem color="#1976d2" label="total" x={0} />
        <LegendItem color="#2e7d32" label="input" x={60} />
        <LegendItem color="#ef6c00" label="output" x={120} />
      </g>
    </svg>
  );
}

function LegendItem({ color, label, x }: { color: string; label: string; x: number }) {
  return (
    <g transform={`translate(${x},0)`}>
      <rect x={0} y={-8} width={14} height={4} fill={color} />
      <text x={20} y={-6} fontSize={11} fill="#444">{label}</text>
    </g>
  );
}

function Bars({ tokens, color = '#1976d2' }: { tokens: { label: string; value: number }[]; color?: string }) {
  const max = Math.max(1, ...tokens.map((t) => t.value || 0));
  return (
    <div>
      {tokens.map((t) => (
        <div key={t.label} style={{ display: 'flex', alignItems: 'center', marginBottom: 6 }}>
          <div style={{ width: 140, fontSize: 12, color: '#444', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.label}>{t.label}</div>
          <div style={{ flex: 1, marginLeft: 8, background: '#f3f4f6', borderRadius: 4, height: 10, position: 'relative' }}>
            <div style={{ width: `${(100 * (t.value || 0)) / max}%`, height: '100%', background: color, borderRadius: 4 }} />
          </div>
          <div style={{ width: 90, textAlign: 'right', fontSize: 12, color: '#666', marginLeft: 8 }}>{(t.value || 0).toLocaleString()}</div>
        </div>
      ))}
      {tokens.length === 0 && <div style={{ fontSize: 12, color: '#666' }}>No data</div>}
    </div>
  );
}


