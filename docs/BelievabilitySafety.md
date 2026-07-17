<!-- Purpose: define deterministic pre-monitoring decoy acceptance evaluation. -->

# Believability and Safety Engine

The Believability and Safety Engine runs after Decoy Generation and before any future placement activation or monitoring. It never mutates a decoy. Given a generated asset, repository/context evidence, and its accepted placement recommendation, it returns an explainable `accept`, `warn`, or `reject` report.

Believability is a configurable weighted average (0–100) of naming realism, context fit, placement compatibility, schema completeness, entropy realism, business realism, and traceability. Default weights are 15, 15, 15, 10, 10, 10, and 10. Safety is independently weighted: inertness 50, collision resistance 25, accidental-use resistance 15, and obvious-trap resistance 10. Default acceptance needs believability ≥80, safety ≥85, collision risk ≤20, and trap risk ≤10. Invalid generation, missing traceability, safety below 70, or collision risk ≥80 always rejects. All remaining outcomes warn.

Collision checking compares normalized payload names against naming samples, services, databases, secret-pattern signals, and configured reserved names. Exact matches are 100 risk; bounded `SequenceMatcher` similarity maps close matches to at most 80 risk. This is O(C) per asset for a bounded corpus C. It deliberately cannot prove a name is unused outside scanned evidence.

Safety checks require inert metadata, non-authentication, the approved `dfg_inert_` secret format, synthetic database safeguards, and no visible `FAKE_SECRET`, `CANARY_TOKEN`, `DO_NOT_USE`, or honeytoken markers. Future GPT critique may add notes or constrained alternatives, but it cannot replace these scoring or acceptance gates. Future monitoring should consume only accepted reports and their trace identifiers.
