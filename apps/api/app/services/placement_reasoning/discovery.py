"""Evidence-backed placement discovery with no writes and no asset generation."""

from app.models.domain.decoy import DecoyKind
from app.models.domain.intelligence import (
    OrganizationContextProfile,
    PlacementCandidate,
    PlacementSignals,
    PlacementTargetType,
    RepositoryIntelligenceProfile,
)


class CandidateDiscovery:
    def discover(
        self, repository: RepositoryIntelligenceProfile, context: OrganizationContextProfile
    ) -> tuple[PlacementCandidate, ...]:
        candidates: list[PlacementCandidate] = []
        for location in repository.secret_locations:
            target_type = (
                PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE
                if "example" in location.path.lower() or "sample" in location.path.lower()
                else PlacementTargetType.ENVIRONMENT_FILE
            )
            candidates.append(
                self._candidate(
                    target_type,
                    location.path,
                    DecoyKind.SECRET,
                    (location.path, *context.environment_naming_conventions),
                )
            )
        if not repository.secret_locations and context.environment_naming_conventions:
            candidates.append(
                self._candidate(
                    PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE,
                    ".env.example",
                    DecoyKind.SECRET,
                    context.environment_naming_conventions,
                )
            )
        for path in self._paths(repository.documentation):
            target_type = (
                PlacementTargetType.ARCHITECTURE_DOCUMENT
                if "architecture" in path.lower() or "design" in path.lower()
                else PlacementTargetType.DOCUMENTATION_FILE
            )
            candidates.append(self._candidate(target_type, path, DecoyKind.DOCUMENT, (path,)))
            if context.ai_exposure_risk >= 0.5:
                candidates.extend(
                    (
                        self._candidate(
                            PlacementTargetType.RAG_DOCUMENT, path, DecoyKind.EMBEDDING, (path,)
                        ),
                        self._candidate(
                            PlacementTargetType.INTERNAL_WIKI_PAGE,
                            f"wiki://internal/{path}",
                            DecoyKind.DOCUMENT,
                            (path,),
                        ),
                    )
                )
        if repository.documentation and context.ai_exposure_risk >= 0.7:
            candidates.append(
                self._candidate(
                    PlacementTargetType.BROWSER_AI_WORKFLOW,
                    "browser-ai://document-workflow",
                    DecoyKind.AGENT_ASSET,
                    ("documentation", "ai_exposure_surface"),
                )
            )
        if repository.databases:
            candidates.append(
                self._candidate(
                    PlacementTargetType.DATABASE_ROW,
                    f"database://{repository.databases[0].name.lower()}/synthetic-row",
                    DecoyKind.DATABASE_RECORD,
                    (repository.databases[0].name,),
                    requires_nonproduction_scope=True,
                )
            )
        for path in self._paths(repository.cicd):
            candidates.append(
                self._candidate(PlacementTargetType.CI_CD_FILE, path, DecoyKind.SECRET, (path,))
            )
        for path in (
            *repository.infrastructure.docker_files,
            *repository.infrastructure.terraform_files,
        ):
            candidates.append(
                self._candidate(PlacementTargetType.CONFIG_FILE, path, DecoyKind.SECRET, (path,))
            )
        for path in self._paths(repository.mcp_configurations):
            candidates.append(
                self._candidate(PlacementTargetType.MCP_CONFIG, path, DecoyKind.MCP_CONFIG, (path,))
            )
        if repository.mcp_configurations and repository.documentation:
            candidates.append(
                self._candidate(
                    PlacementTargetType.AGENT_ACCESSIBLE_FOLDER,
                    "documentation://agent-accessible",
                    DecoyKind.AGENT_ASSET,
                    ("mcp", "documentation"),
                )
            )
        for folder in repository.folder_structure:
            name = folder.lower().rstrip("/")
            if name in {"scripts", "legacy", "migrations"}:
                candidates.append(
                    self._candidate(
                        PlacementTargetType.LEGACY_SCRIPT, f"{folder}/", DecoyKind.SECRET, (folder,)
                    )
                )
            if name in {"data", "exports", "reports"}:
                candidates.extend(
                    (
                        self._candidate(
                            PlacementTargetType.SPREADSHEET_ROW,
                            f"{folder}/",
                            DecoyKind.SPREADSHEET_ROW,
                            (folder,),
                        ),
                        self._candidate(
                            PlacementTargetType.EXPORTABLE_REPORT,
                            f"{folder}/",
                            DecoyKind.DOCUMENT,
                            (folder,),
                        ),
                    )
                )
        return tuple(
            sorted(candidates, key=lambda item: (item.target_type.value, item.target_location))
        )

    @staticmethod
    def _paths(items: tuple[object, ...]) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    value
                    for item in items
                    for value in getattr(item, "evidence", ())
                    if "/" in value or "." in value
                }
            )
        )

    @staticmethod
    def _candidate(
        target_type: PlacementTargetType,
        target_location: str,
        future_asset_type: DecoyKind,
        evidence: tuple[str, ...],
        *,
        requires_nonproduction_scope: bool = False,
    ) -> PlacementCandidate:
        return PlacementCandidate(
            target_type=target_type,
            target_location=target_location,
            future_asset_type=future_asset_type,
            evidence=tuple(sorted(set(evidence))),
            signals=_signals(target_type),
            requires_nonproduction_scope=requires_nonproduction_scope,
        )


def _signals(target_type: PlacementTargetType) -> PlacementSignals:
    values = {
        PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE: (
            0.85,
            0.8,
            0.55,
            0.75,
            0.7,
            0.9,
            0.9,
            0.9,
            0.1,
        ),
        PlacementTargetType.ENVIRONMENT_FILE: (0.9, 0.75, 0.65, 0.8, 0.8, 0.85, 0.2, 0.9, 0.7),
        PlacementTargetType.DOCUMENTATION_FILE: (0.8, 0.8, 0.65, 0.8, 0.75, 0.9, 0.9, 0.85, 0.15),
        PlacementTargetType.ARCHITECTURE_DOCUMENT: (
            0.85,
            0.85,
            0.65,
            0.8,
            0.7,
            0.85,
            0.85,
            0.9,
            0.15,
        ),
        PlacementTargetType.RAG_DOCUMENT: (0.85, 0.95, 0.6, 0.85, 0.75, 0.8, 0.8, 0.9, 0.2),
        PlacementTargetType.CI_CD_FILE: (0.8, 0.75, 0.6, 0.7, 0.65, 0.85, 0.7, 0.85, 0.3),
        PlacementTargetType.MCP_CONFIG: (0.85, 0.95, 0.6, 0.7, 0.65, 0.9, 0.7, 0.95, 0.3),
        PlacementTargetType.AGENT_ACCESSIBLE_FOLDER: (
            0.8,
            0.9,
            0.6,
            0.75,
            0.7,
            0.8,
            0.85,
            0.85,
            0.2,
        ),
        PlacementTargetType.LEGACY_SCRIPT: (0.7, 0.65, 0.65, 0.65, 0.6, 0.8, 0.75, 0.7, 0.25),
        PlacementTargetType.SPREADSHEET_ROW: (0.7, 0.65, 0.7, 0.9, 0.8, 0.75, 0.65, 0.75, 0.35),
        PlacementTargetType.EXPORTABLE_REPORT: (0.8, 0.75, 0.7, 0.95, 0.85, 0.8, 0.8, 0.8, 0.2),
        PlacementTargetType.DATABASE_ROW: (0.85, 0.65, 0.75, 0.9, 0.8, 0.85, 0.5, 0.9, 0.5),
        PlacementTargetType.CONFIG_FILE: (0.75, 0.65, 0.6, 0.65, 0.6, 0.8, 0.75, 0.8, 0.25),
        PlacementTargetType.INTERNAL_WIKI_PAGE: (0.75, 0.8, 0.7, 0.8, 0.75, 0.75, 0.85, 0.7, 0.2),
        PlacementTargetType.BROWSER_AI_WORKFLOW: (0.7, 0.9, 0.5, 0.7, 0.7, 0.6, 0.7, 0.7, 0.4),
    }[target_type]
    return PlacementSignals(
        attacker_visibility=values[0],
        ai_agent_access=values[1],
        insider_access=values[2],
        exportability=values[3],
        accidental_exposure=values[4],
        plausibility=values[5],
        safety=values[6],
        context_alignment=values[7],
        false_positive_risk=values[8],
    )
