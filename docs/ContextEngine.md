<!-- Purpose: define deterministic organization-context inference. -->

# Context Engine

The Context Engine converts a `RepositoryIntelligenceProfile` into a stable, serializable `OrganizationContextProfile`. It is downstream of Repository Intelligence: the scanner observes repository evidence; this module classifies and ranks it. It does not read repositories, generate decoys, call AI models, alert, or monitor.

Its five independently testable layers are feature extraction, normalization, classification, scoring, and profile assembly. Naming vocabulary and environment conventions influence normalized vocabulary and configuration-zone ranking. Classification is deterministic rules over evidence; confidence combines evidence count and scan completeness. Sparse input stays explicitly `unknown` rather than inventing context.

The resulting profile exposes organization archetype, stack maturity, vocabulary, sensitive assets, ranked placement zones, workflow surfaces, AI exposure risk, database confidence, documentation culture, explainability, and confidence metadata. Decoy generation, placement, coverage, and incident explanation can consume it without depending on a scanner implementation.
