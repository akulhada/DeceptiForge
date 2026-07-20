<!-- Purpose: document agent scope policies, path classification, path normalization safety, and the
deterministic explainable scoring. -->

# Agent scope policies

A scope policy bounds what an agent session may touch. It is deterministic and versioned.

## Fields

`allowed_paths`, `denied_paths` (glob patterns; `dir/**` matches a directory subtree),
`allowed_tools`, `denied_tools`, `allowed_resource_types`, `maximum_file_reads`,
`maximum_sensitive_reads`, and the boolean gates `allow_dependency_changes`,
`allow_secret_file_access`, `allow_database_access`, `allow_network_access`. `policy_version` is
monotonic. Bounds: `AGENT_SCOPE_MAX_ALLOWED_PATHS`, `AGENT_SCOPE_MAX_DENIED_PATHS`.

Example — task "Fix the mobile navbar spacing":

```
allowed_paths: apps/web/components/navigation/**, related styles/tests
denied: auth, billing, environment files
allow_database_access: false   allow_network_access: false
```

## Path normalization (safety)

Every reported path is normalized (`app/services/agent_sensor/paths.py`) before any policy check.
Normalization **rejects** path traversal (`..`), percent-encoded traversal, absolute and Windows
drive paths, null bytes, and repository-root escapes, and canonicalizes backslashes and `./`
segments. Matching is case-insensitive so case tricks cannot bypass a rule. A path that cannot be
safely normalized never silently counts as in-scope.

## Path classification

Normalized paths are classified deterministically (`classify_path`): `decoy`, `credential`,
`authentication`, `billing`, `customer_data`, `deployment`, `build_output`, `generated`,
`shared_dependency`, `task_relevant`, `adjacent`, or `unrelated`. Sensitive classes (credential,
auth, billing, deployment, customer-data, sensitive) elevate severity and count toward the
sensitive-read cap. A single permitted shared-dependency read is not treated as malicious.

## Explainable scoring

The engine scores each event against the policy and a bounded running aggregate, considering
distance from allowed paths, sensitivity, decoy contact, unrelated-path breadth, repeated access,
tool type, destructive intent, explicit deny rules, and cross-surface activity. Decoy contact
strongly increases severity. Every decision returns the exact policy rule and a human explanation;
incident severity is deterministic (`incident_severity`) and never assigned by GPT.

## Sequence analysis

Bounded session sequence analysis (`app/services/agent_sensor/sequence.py`) flags escalation —
unrelated/adjacent probing followed by sensitive or decoy access — and produces a content-free
session summary. Algorithms are bounded (no O(n²) full-history scans).
