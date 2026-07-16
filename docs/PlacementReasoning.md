<!-- Purpose: define deterministic, safety-filtered placement planning. -->

# Placement Reasoning Engine

The Placement Reasoning Engine transforms a `RepositoryIntelligenceProfile` and an `OrganizationContextProfile` into a ranked `PlacementPlan`. It recommends where a future asset could be placed. It does not generate assets, write to repositories, deploy anything, monitor access, or call an AI model.

`CandidateDiscovery` derives only repository-evidenced zones: environment files, documentation, databases, CI/CD, infrastructure configuration, MCP configuration, agent-accessible documentation, and legacy/export/report folders. `PlacementScorer` applies a fixed formula:

- `detection_quality = .30 attacker + .20 AI + .15 insider + .15 export + .10 accidental + .10 plausibility`
- `priority = .40 detection_quality + .25 visibility + .20 context_alignment + .15 safety`
- `risk = 1 - safety`

Confidence combines safety, context alignment, the Context Engine confidence, and bounded evidence count. Candidates are rejected before ranking when they target production environment files, need an explicit non-production database scope, fall below `.65` safety, or exceed `.45` false-positive risk. Accepted candidates are ranked by priority, confidence, then location, making output deterministic.

The later Decoy Generator may consume only accepted recommendations and their asset-type hints. Monitoring and incident reconstruction can use the target, score, explanation, and evidence to establish detection expectations and narrate an observed interaction. Discovery and scoring are O(C), and ranking is O(C log C), where C is the usually-small candidate count.
