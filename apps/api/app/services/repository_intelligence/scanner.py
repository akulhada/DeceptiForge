# Purpose: orchestrate the repository intelligence pipeline.
# Responsibilities: run one bounded crawl, apply injectable analyzers, and build a profile.
# Dependencies: the crawler, the analyzer contract, and the profile builder.
from __future__ import annotations

from pathlib import Path

from app.models.domain.intelligence import RepositoryIntelligenceProfile
from app.services.repository_intelligence.analyzers import RepositoryAnalyzer, default_analyzers
from app.services.repository_intelligence.builder import ProfileBuilder
from app.services.repository_intelligence.evidence import RepositoryCrawler


class LocalRepositoryScanner:
    """Composes a single crawl with independent analyzers into a repository profile.

    Purpose: turn a local repository path into a strongly typed intelligence profile.
    Arguments: ``analyzers`` overrides the default pipeline; ``crawler`` and ``builder`` allow
      substitution for testing. Returns: a RepositoryIntelligenceProfile.
    Complexity: O(files) dominated by the crawl; analyzers are linear over bounded evidence.
    Edge cases: an empty or unreadable repository yields an empty-but-valid profile; the profile
      never contains raw source content.
    """

    def __init__(
        self,
        analyzers: tuple[RepositoryAnalyzer, ...] | None = None,
        *,
        crawler: RepositoryCrawler | None = None,
        builder: ProfileBuilder | None = None,
    ) -> None:
        self._crawler = crawler or RepositoryCrawler()
        self._analyzers = default_analyzers() if analyzers is None else tuple(analyzers)
        self._builder = builder or ProfileBuilder()

    def scan(self, root: Path) -> RepositoryIntelligenceProfile:
        evidence = self._crawler.crawl(Path(root))
        contributions = tuple(analyzer.analyze(evidence) for analyzer in self._analyzers)
        return self._builder.build(evidence, contributions)
