# Purpose: match an agent activity event to a registered decoy by metadata (no raw content).
# Responsibilities: hold a bounded, org-scoped index of decoy trace ids, normalized decoy paths, and
#   resource-id hashes, and resolve an event to a decoy id using trace id, path, or resource hash.
#   Metadata is sufficient; raw content matching is never required. Pure.
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DecoyIndex:
    trace_ids: dict[str, str] = field(default_factory=dict)  # trace_id -> decoy_id
    paths: dict[str, str] = field(default_factory=dict)  # normalized lower path -> decoy_id
    resource_hashes: dict[str, str] = field(default_factory=dict)  # resource_id_hash -> decoy_id

    def path_set(self) -> frozenset[str]:
        return frozenset(self.paths)


def resolve_decoy(
    *,
    trace_id: str | None,
    normalized_path: str | None,
    resource_id_hash: str | None,
    index: DecoyIndex,
) -> str | None:
    if trace_id and trace_id in index.trace_ids:
        return index.trace_ids[trace_id]
    if normalized_path and normalized_path.lower() in index.paths:
        return index.paths[normalized_path.lower()]
    if resource_id_hash and resource_id_hash in index.resource_hashes:
        return index.resource_hashes[resource_id_hash]
    return None
