<!-- Purpose: document the Repository Intelligence Engine. Responsibilities: explain the analyzer
pipeline, its contracts, and how to extend it. Future modules: update when new analyzers or
evidence sources are approved. -->

# Repository Intelligence Engine

The Repository Intelligence Engine turns a local repository path into a strongly typed
`RepositoryIntelligenceProfile`. It is the foundation every later DeceptiForge module
(context, placement, decoy generation) consumes. It performs **no** deception and makes **no**
LLM calls — it is fully deterministic.

## Pipeline

```text
LocalRepositoryScanner (orchestrator)
  │
  ├─ RepositoryCrawler ──► RepositoryEvidence     one bounded filesystem pass
  │
  ├─ analyzers: tuple[RepositoryAnalyzer]         pure evidence → AnalyzerContribution
  │
  └─ ProfileBuilder ──► RepositoryIntelligenceProfile
```

The central decision is **one traversal, many pure analyzers**. Analyzers never touch the
filesystem; they read a shared, immutable evidence bundle produced by a single crawl. This keeps
I/O at O(files) no matter how many analyzers exist, and makes every analyzer a pure function that
is trivial to unit-test.

## Components

| Component | Responsibility |
| --- | --- |
| `RepositoryCrawler` | One bounded `os.walk`. Produces `RepositoryEvidence` (paths, extension counts, bounded text fragments, git flag). Prunes ignored directories, caps files and text bytes, flags `truncated`. |
| `RepositoryEvidence` | Immutable crawl output. Holds text fragments transiently; they are never serialized into a profile. |
| `RepositoryAnalyzer` | `Protocol`: `name` + `analyze(evidence) -> AnalyzerContribution`. The extension point. |
| `AnalyzerContribution` | Immutable partial profile with empty defaults, so contributions fold by concatenation. |
| `ProfileBuilder` | Folds contributions and derives profile-level fields (folder structure, technologies). No I/O. |
| `LocalRepositoryScanner` | Wires crawler + analyzers + builder. Analyzers are constructor-injectable. |

## Analyzers

| Analyzer | Emits |
| --- | --- |
| `LanguageAnalyzer` | languages (by file extension) |
| `FrameworkAnalyzer` | frameworks (signature files, fragments) |
| `PackageManagerAnalyzer` | package managers (lockfiles, manifests) |
| `ServiceAnalyzer` | service / worker names (file stems) |
| `DatabaseAnalyzer` | database technologies (fragments) |
| `CloudAnalyzer` | cloud provider hints (fragments, paths) |
| `InfrastructureAnalyzer` | Docker, Terraform, Kubernetes files |
| `CicdAnalyzer` | CI/CD providers (GitHub Actions, GitLab CI, Jenkins, CircleCI, Azure Pipelines, Drone, Bitbucket, Travis) |
| `SecretPatternAnalyzer` | secret-bearing paths and their exposure risk areas |
| `DocumentationAnalyzer` | documentation surfaces (bounded) |
| `McpAnalyzer` | presence of MCP configuration surfaces |
| `NamingAnalyzer` | naming profile (adapts `NamingPatternInferenceEngine`) |

## Complexity and bounds

- **Time:** O(files); the crawl dominates. Analyzers are linear over already-collected evidence.
- **Space:** bounded by `max_text_files * max_text_bytes` (default ≈ 4 MB), independent of repo size.
- **Limits:** ≤ 10,000 files, ≤ 200 text files, ≤ 20,000 bytes per text file; overflow sets
  `truncated=True`.

## Security posture

- No raw source content is stored in the profile — only derived, named evidence. This is
  enforced by test and by keeping fragments inside the transient evidence bundle.
- The crawler prunes `.git`, `node_modules`, `vendor`, `dist`, `build`, `__pycache__`, `.venv`.

## Extending the pipeline

Implement the contract and inject it — no changes to the crawler or builder are needed when
contributing to existing fields:

```python
from app.services.repository_intelligence import (
    AnalyzerContribution,
    LocalRepositoryScanner,
    RepositoryEvidence,
    default_analyzers,
)


class LicenseAnalyzer:
    name = "license"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        ...  # read evidence, return a contribution


scanner = LocalRepositoryScanner(analyzers=(*default_analyzers(), LicenseAnalyzer()))
profile = scanner.scan(repo_path)
```

## Why synchronous

`scan` is synchronous by design. A single local `os.walk` is syscall-bound; async I/O adds
complexity without speeding up one sequential traversal. Async belongs only in an analyzer that
performs network I/O (for example a future GitHub-API analyzer), introduced scoped to that
analyzer rather than forced onto the whole pipeline.

## Usage

```python
from pathlib import Path
from app.services.repository_intelligence import LocalRepositoryScanner

profile = LocalRepositoryScanner().scan(Path("/path/to/repo"))
```
