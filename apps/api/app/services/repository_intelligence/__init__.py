"""Deterministic repository intelligence: crawl, analyze, build a typed profile.

The public surface is the scanner plus the extension primitives (the analyzer contract,
contribution type, crawler, evidence, and builder) needed to add or replace analyzers.
"""

from app.services.repository_intelligence.analyzers import (
    AnalyzerContribution,
    RepositoryAnalyzer,
    default_analyzers,
)
from app.services.repository_intelligence.builder import ProfileBuilder
from app.services.repository_intelligence.evidence import (
    FileEntry,
    RepositoryCrawler,
    RepositoryEvidence,
)
from app.services.repository_intelligence.naming import (
    NamingCorpus,
    NamingPatternInferenceEngine,
)
from app.services.repository_intelligence.scanner import LocalRepositoryScanner

__all__ = [
    "AnalyzerContribution",
    "FileEntry",
    "LocalRepositoryScanner",
    "NamingCorpus",
    "NamingPatternInferenceEngine",
    "ProfileBuilder",
    "RepositoryAnalyzer",
    "RepositoryCrawler",
    "RepositoryEvidence",
    "default_analyzers",
]
