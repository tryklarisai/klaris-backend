import React from "react";
import embed from "vega-embed";

export default function ChartRenderer({ spec, onRendered }: { spec: any; onRendered?: () => void }) {
  const wrapperRef = React.useRef<HTMLDivElement>(null);
  const innerRef = React.useRef<HTMLDivElement>(null);
  const viewRef = React.useRef<any>(null);
  const [exportMode, setExportMode] = React.useState(false);
  const [imgUrl, setImgUrl] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!innerRef.current) return;
    let view: any;
    let cancelled = false;
    (async () => {
      try {
        const result = await embed(innerRef.current!, spec as any, { actions: false });
        if (!cancelled) {
          view = result.view;
          viewRef.current = view;
        }
        try { onRendered && onRendered(); } catch {}
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn('Failed to render chart', e);
      }
    })();
    return () => { try { cancelled = true; view && view.finalize && view.finalize(); } catch {} };
  }, [spec]);

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
    <div ref={wrapperRef}>
      {exportMode && imgUrl ? (
        <img src={imgUrl} alt="chart" style={{ width: '100%', height: 'auto' }} />
      ) : (
        <div ref={innerRef} />
      )}
    </div>
  );
}


