// Purpose: render a minimized evidence excerpt with its location and digest.
// Responsibilities: display forensic evidence compactly without exposing full payloads.
export function EvidenceExcerpt({
  excerpt,
  location,
  digest,
}: {
  excerpt: string;
  location: string;
  digest?: string;
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-2 font-mono text-xs">
      <div className="text-slate-500">{location}</div>
      <div className="mt-1 break-all text-slate-300">{excerpt}</div>
      {digest ? <div className="mt-1 truncate text-[10px] text-slate-600">sha256:{digest}</div> : null}
    </div>
  );
}
