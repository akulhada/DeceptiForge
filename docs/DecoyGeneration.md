<!-- Purpose: define template-constrained generation of safe decoy assets. -->

# Decoy Generator

The Decoy Generator consumes only accepted `PlacementPlan.recommendations`; it never chooses a placement and ignores `rejected_candidates`. It creates validated `DecoyAsset` records for three MVP families: inert secret metadata, short internal documents, and synthetic database records. MCP, RAG, spreadsheet, package, browser, monitoring, and alerting assets are deliberately unsupported.

Each recommendation is admitted only when it remains high-confidence and below the false-positive-risk threshold. The `DecoyTemplateRegistry` selects a versioned allow-listed template by decoy kind and target type. `PayloadGenerators` derives names, body content, and fake values from organization vocabulary and a UUIDv5 trace identifier. Secrets are SHA-256-derived strings beginning `dfg_inert_`, explicitly marked non-authenticating, and never use live credentials. Database records use deterministic organizations and `invalid.example`, never a real person or customer.

The validation pipeline checks Pydantic schema shape, template/placement compatibility, naming collisions against observed samples and reserved names, safety invariants, traceability, and JSON serialization. Invalid output is reported in `rejected_candidates`, never in `assets`. The generated asset also supplies believability inputs, collision evidence, unconfigured trigger metadata, and rotation guidance for future monitoring.

Generation is O(P × C), where P is accepted placements and C is observed/reserved names. A future GPT adapter may propose text only after a template has been selected; its output must be normalized into the same payload contracts and pass the unchanged validation pipeline.
