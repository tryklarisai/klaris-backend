import React from "react";
import embed from "vega-embed";

export default function ChartRenderer({ spec, onRendered }: { spec: any; onRendered?: () => void }) {
  const wrapperRef = React.useRef<HTMLDivElement>(null);
  const innerRef = React.useRef<HTMLDivElement>(null);
  const viewRef = React.useRef<any>(null);
  const [exportMode, setExportMode] = React.useState(false);
  const [imgUrl, setImgUrl] = React.useState<string | null>(null);
  const [containerWidth, setContainerWidth] = React.useState<number>(0);

  // Observe width changes of the wrapper; charts often mount before layout assigns width
  React.useLayoutEffect(() => {
    const el = wrapperRef.current;
    if (!el || typeof (window as any).ResizeObserver === 'undefined') return;
    const ro = new (window as any).ResizeObserver((entries: any[]) => {
      for (const entry of entries) {
        const cr = entry.contentRect || entry.target.getBoundingClientRect();
        const w = Math.max(0, Math.floor(cr?.width || 0));
        setContainerWidth((prev) => (prev !== w ? w : prev));
      }
    });
    try { ro.observe(el); } catch {}
    // Initialize once
    try {
      const rect = el.getBoundingClientRect();
      const w = Math.max(0, Math.floor(rect?.width || 0));
      setContainerWidth((prev) => (prev !== w ? w : prev));
    } catch {}
    return () => { try { ro.disconnect(); } catch {} };
  }, []);

  React.useEffect(() => {
    if (!innerRef.current) return;
    let view: any;
    let cancelled = false;
    (async () => {
      try {
        // Determine available container width; if zero, fall back to a sensible width
        const cw = containerWidth || (wrapperRef.current?.getBoundingClientRect().width || 0);
        const specToUse = (() => {
          try {
            const clone = JSON.parse(JSON.stringify(spec || {}));
            if (!clone || typeof clone !== 'object') return spec;
            if (!clone.autosize) clone.autosize = { type: 'fit', contains: 'padding' };
            if (!clone.width || cw === 0) {
              clone.width = cw > 0 ? cw : 640;
            }
            if (!clone.height) clone.height = 280;
            return clone;
          } catch { return spec; }
        })();
        // Debug: log the spec we are about to render (use console.log for visibility)
        try { console.log('[ChartRenderer] rendering spec:', specToUse); } catch {}
        const result = await embed(innerRef.current!, specToUse as any, { actions: false, renderer: 'canvas' });
        if (!cancelled) {
          view = result.view;
          viewRef.current = view;
        }
        try {
          const el = innerRef.current!;
          const parent = wrapperRef.current?.parentElement as HTMLElement | null;
          const parentW = parent ? parent.getBoundingClientRect().width : undefined;
          const wrapW = wrapperRef.current?.getBoundingClientRect().width || 0;
          console.log('[ChartRenderer] mounted metrics:', { htmlLen: (el.innerHTML || '').length, w: el.clientWidth, h: el.clientHeight, wrapW, parentW });
        } catch {}
        try { onRendered && onRendered(); } catch {}
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error('Failed to render chart with spec:', spec, e);
      }
    })();
    return () => { try { cancelled = true; view && view.finalize && view.finalize(); } catch {} };
  }, [spec, containerWidth]);

  React.useEffect(() => {
    async function toImage() {
      try {
        const v = viewRef.current;
        if (!v) return;
        const canvas = await v.toCanvas();
        const url = canvas.toDataURL('image/png');
        setImgUrl(url);
        setExportMode(true);
        try { if (wrapperRef.current) (wrapperRef.current as any).dataset.exportReady = 'image'; } catch {}
      } catch (e) {
        // ignore
      }
    }
    function onPrepare() { toImage(); }
    function onRestore() {
      setExportMode(false);
      setImgUrl(null);
      try { if (wrapperRef.current) delete (wrapperRef.current as any).dataset.exportReady; } catch {}
    }
    window.addEventListener('chat:export:prepare', onPrepare as any);
    window.addEventListener('chat:export:restore', onRestore as any);
    return () => {
      window.removeEventListener('chat:export:prepare', onPrepare as any);
      window.removeEventListener('chat:export:restore', onRestore as any);
    };
  }, []);

  return (
    <div ref={wrapperRef} style={{ width: '100%', minWidth: 0, display: 'block' }}>
      {exportMode && imgUrl ? (
        <img src={imgUrl} alt="chart" style={{ width: '100%', height: 'auto' }} />
      ) : (
        <div ref={innerRef} style={{ width: '100%', minWidth: 0 }} />
      )}
    </div>
  );
}


