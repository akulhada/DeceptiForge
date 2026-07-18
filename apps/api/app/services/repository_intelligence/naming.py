"""Bounded lexical naming-convention inference; no source content is persisted."""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from difflib import SequenceMatcher
from math import log2
from pathlib import PurePath

from pydantic import Field

from app.models.domain.base import DomainModel
from app.models.domain.intelligence import (
    NamingCategory,
    NamingConvention,
    NamingProfile,
    NamingStyle,
    Separator,
    SeparatorUsage,
    VocabularyTerm,
)

_ENV = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_SQL = re.compile(
    r"\b(?:create\s+table|from|join|into|update|references)\s+(?:[\"`\[])?([A-Za-z_][A-Za-z0-9_$]*)",
    re.IGNORECASE,
)
_ROUTE = re.compile(r"[\"'](/(?:[A-Za-z0-9_{}-]+/)*[A-Za-z0-9_{}-]+)[\"']")
_SPLIT = re.compile(r"[_\-./]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_IGNORED = (".git", "node_modules", "vendor", "dist", "build", "__pycache__")


class NamingSourceFile(DomainModel):
    path: str = Field(min_length=1, max_length=2048)
    content: str = Field(max_length=200_000)


class NamingCorpus(DomainModel):
    file_paths: tuple[str, ...] = ()
    text_fragments: tuple[str, ...] = ()
    environment_variables: tuple[str, ...] = ()
    service_names: tuple[str, ...] = ()
    database_names: tuple[str, ...] = ()
    api_names: tuple[str, ...] = ()
    resource_names: tuple[str, ...] = ()
    source_files: tuple[NamingSourceFile, ...] = ()
    vocabulary_aliases: dict[str, str] = Field(default_factory=dict)


class NamingPatternInferenceEngine:
    """Frequency, tokenization, style clustering, and bounded fuzzy vocabulary grouping."""

    def infer(self, corpus: NamingCorpus) -> NamingProfile:
        names = self._collect(corpus)
        conventions = tuple(
            item
            for category, values in sorted(names.items(), key=lambda item: item[0].value)
            for item in self._conventions(category, values)
        )
        all_names = tuple(value for values in names.values() for value in values)
        return NamingProfile(
            naming_style=conventions,
            common_prefixes=self._affixes(all_names, True),
            common_suffixes=self._affixes(all_names, False),
            vocabulary=self._vocabulary(all_names, corpus.vocabulary_aliases),
            separators=self._separators(conventions),
            confidence=self._confidence(conventions),
        )

    def _collect(self, corpus: NamingCorpus) -> dict[NamingCategory, set[str]]:
        names: dict[NamingCategory, set[str]] = defaultdict(set)
        names[NamingCategory.ENVIRONMENT_VARIABLE].update(corpus.environment_variables)
        names[NamingCategory.SERVICE].update(corpus.service_names)
        names[NamingCategory.DATABASE].update(corpus.database_names)
        names[NamingCategory.RESOURCE].update(corpus.resource_names)
        for path_text in corpus.file_paths:
            path = PurePath(path_text)
            if self._ignored(path) or path.name.startswith(".") or not path.stem:
                continue
            names[NamingCategory.FILE].add(path.stem)
            names[NamingCategory.FOLDER].update(
                part for part in path.parts[:-1] if not part.startswith(".")
            )
            if path.stem.endswith(("-service", "_service", "-worker", "_worker")):
                names[NamingCategory.SERVICE].add(path.stem)
        for text in (*corpus.text_fragments, *(file.content for file in corpus.source_files)):
            names[NamingCategory.ENVIRONMENT_VARIABLE].update(_ENV.findall(text))
            names[NamingCategory.DATABASE].update(_SQL.findall(text))
            for route in _ROUTE.findall(text):
                self._route(names, route)
        for route in corpus.api_names:
            self._route(names, route)
        for source in corpus.source_files:
            if source.path.endswith(".py") and not self._ignored(PurePath(source.path)):
                try:
                    tree = ast.parse(source.content)
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr
                        in {"get", "post", "put", "patch", "delete", "route", "add_api_route"}
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        self._route(names, node.args[0].value)
        return names

    @staticmethod
    def _ignored(path: PurePath) -> bool:
        return any(part in _IGNORED for part in path.parts)

    @staticmethod
    def _route(names: dict[NamingCategory, set[str]], route: str) -> None:
        for segment in route.strip("/").split("/"):
            if segment and not segment.startswith("{") and segment not in {"api", "v1", "v2", "v3"}:
                names[NamingCategory.API].add(segment)
                names[NamingCategory.RESOURCE].add(segment)

    def _conventions(
        self, category: NamingCategory, values: Iterable[str]
    ) -> tuple[NamingConvention, ...]:
        groups: dict[tuple[NamingStyle, Separator], list[str]] = defaultdict(list)
        for value in sorted(set(values)):
            if self._tokens(value) and " " not in value and len(value) <= 512:
                groups[self._style(value)].append(value)
        total = sum(map(len, groups.values()))
        return (
            tuple(
                NamingConvention(
                    category=category,
                    style=style,
                    separator=separator,
                    support=len(group),
                    confidence=round(len(group) / total, 3),
                    samples=tuple(group[:5]),
                )
                for (style, separator), group in sorted(
                    groups.items(), key=lambda entry: entry[0][0].value
                )
            )
            if total
            else ()
        )

    @staticmethod
    def _style(value: str) -> tuple[NamingStyle, Separator]:
        if "_" in value:
            return (
                NamingStyle.SCREAMING_SNAKE if value.isupper() else NamingStyle.SNAKE,
                Separator.UNDERSCORE,
            )
        if "-" in value:
            return NamingStyle.KEBAB, Separator.HYPHEN
        if "." in value:
            return NamingStyle.DOT, Separator.DOT
        if value.isupper():
            return NamingStyle.FLAT_UPPER, Separator.NONE
        if value.islower():
            return NamingStyle.FLAT_LOWER, Separator.NONE
        return (NamingStyle.PASCAL if value[:1].isupper() else NamingStyle.CAMEL), Separator.NONE

    @staticmethod
    def _tokens(value: str) -> tuple[str, ...]:
        return tuple(token for token in _SPLIT.split(_CAMEL.sub(" ", value).lower()) if token)

    def _affixes(self, names: Iterable[str], first: bool) -> tuple[str, ...]:
        counts = Counter(
            tokens[0 if first else -1] for name in names if (tokens := self._tokens(name))
        )
        return tuple(value for value, count in counts.most_common(10) if count >= 2)

    def _vocabulary(
        self, names: Iterable[str], aliases: dict[str, str]
    ) -> tuple[VocabularyTerm, ...]:
        normalized = {key.lower(): value.lower() for key, value in aliases.items()}
        counts = Counter(
            normalized.get(token, token) for name in names for token in self._tokens(name)
        )
        clusters: list[list[str]] = []
        for token in sorted(counts, key=lambda value: (-counts[value], value))[:256]:
            match = next(
                (
                    cluster
                    for cluster in clusters
                    if token[:3] == cluster[0][:3]
                    and SequenceMatcher(a=token, b=cluster[0]).ratio() >= 0.9
                ),
                None,
            )
            (
                (match if match is not None else clusters.append([token])).append(token)
                if match is not None
                else None
            )
        return tuple(
            VocabularyTerm(value=cluster[0], support=sum(counts[value] for value in cluster))
            for cluster in clusters
            if sum(counts[value] for value in cluster) >= 2
        )

    @staticmethod
    def _separators(conventions: tuple[NamingConvention, ...]) -> tuple[SeparatorUsage, ...]:
        counts: Counter[Separator] = Counter()
        for convention in conventions:
            counts[convention.separator] += convention.support
        total = sum(counts.values())
        return (
            tuple(
                SeparatorUsage(separator=value, support=count, confidence=round(count / total, 3))
                for value, count in counts.most_common()
            )
            if total
            else ()
        )

    @staticmethod
    def _confidence(conventions: tuple[NamingConvention, ...]) -> float:
        total = sum(item.support for item in conventions)
        if not total:
            return 0.0
        dominant = sum(
            max((item.support for item in conventions if item.category == category), default=0)
            for category in NamingCategory
        )
        return round((dominant / total) * min(1.0, log2(total + 1) / 3), 3)
