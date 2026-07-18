// Purpose: render an incident's ordered forensic timeline.
// Responsibilities: show each observation as a sequenced node with evidence. Dependencies: types.
import { EvidenceExcerpt } from './EvidenceExcerpt';
import type { TimelineEntry } from '@/services/types';

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <ol className="relative space-y-4 border-l border-slate-800 pl-5">
      {entries.map((entry) => (
        <li key={entry.sequence} className="relative">
          <span className="absolute -left-[23px] top-1 h-3 w-3 rounded-full border-2 border-sky-500 bg-slate-950" />
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span className="font-medium text-slate-200">#{entry.sequence}</span>
            <span>{entry.monitor_type}</span>
            <span>·</span>
            <span>{new Date(entry.timestamp).toLocaleString()}</span>
            <span>·</span>
            <span>confidence {Math.round(entry.confidence * 100)}%</span>
          </div>
          <p className="mt-1 text-sm text-slate-200">{entry.summary}</p>
          <div className="mt-2">
            <EvidenceExcerpt
              excerpt={entry.evidence.excerpt}
              location={entry.evidence.location}
              digest={entry.evidence.digest}
            />
          </div>
        </li>
      ))}
    </ol>
  );
}
