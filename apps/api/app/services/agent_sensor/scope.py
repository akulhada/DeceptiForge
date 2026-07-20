# Purpose: deterministic task-scope normalization for an agent session.
# Responsibilities: sanitize + bound the task summary, normalize allowed/denied path patterns, and
#   snapshot a bounded, JSON-serializable scope. Deterministic first; any optional GPT scope
#   suggestion is advisory only and never the final enforcement decision. Pure.
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.services.agent_sensor.minimize import sanitize_task_summary
from app.services.agent_sensor.paths import normalize_path


@dataclass(frozen=True)
class NormalizedScope:
    task_summary: str
    allowed_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    denied_tools: tuple[str, ...] = ()
    allowed_resource_types: tuple[str, ...] = ()
    keywords: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> str:
        return json.dumps(
            {
                "task_summary": self.task_summary,
                "allowed_paths": list(self.allowed_paths),
                "denied_paths": list(self.denied_paths),
                "allowed_tools": list(self.allowed_tools),
                "denied_tools": list(self.denied_tools),
                "allowed_resource_types": list(self.allowed_resource_types),
                "keywords": list(self.keywords),
            },
            separators=(",", ":"),
        )


_STOPWORDS = frozenset(
    {"the", "a", "an", "fix", "to", "in", "on", "of", "and", "for", "with", "add", "update"}
)


def _keywords(summary: str) -> tuple[str, ...]:
    words = [w.strip(".,:;()").lower() for w in summary.split()]
    return tuple(dict.fromkeys(w for w in words if len(w) >= 3 and w not in _STOPWORDS))[:12]


def _norm_patterns(patterns: tuple[str, ...], limit: int) -> tuple[str, ...]:
    out: list[str] = []
    for p in patterns:
        n = normalize_path(p.rstrip("/*")) if not p.endswith("/**") else normalize_path(p[:-3])
        if n is None:
            continue
        out.append(f"{n}/**" if p.endswith(("/**", "/")) else n)
        if len(out) >= limit:
            break
    return tuple(dict.fromkeys(out))


def normalize_scope(
    *,
    task_summary: str,
    allowed_paths: tuple[str, ...] = (),
    denied_paths: tuple[str, ...] = (),
    allowed_tools: tuple[str, ...] = (),
    denied_tools: tuple[str, ...] = (),
    allowed_resource_types: tuple[str, ...] = (),
    max_allowed: int = 200,
    max_denied: int = 200,
) -> NormalizedScope:
    summary = sanitize_task_summary(task_summary)
    return NormalizedScope(
        task_summary=summary,
        allowed_paths=_norm_patterns(allowed_paths, max_allowed),
        denied_paths=_norm_patterns(denied_paths, max_denied),
        allowed_tools=tuple(dict.fromkeys(t.strip().lower() for t in allowed_tools if t.strip())),
        denied_tools=tuple(dict.fromkeys(t.strip().lower() for t in denied_tools if t.strip())),
        allowed_resource_types=tuple(
            dict.fromkeys(r.strip().lower() for r in allowed_resource_types if r.strip())
        ),
        keywords=_keywords(summary),
    )
