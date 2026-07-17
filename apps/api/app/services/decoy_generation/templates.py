"""Allow-listed template metadata; generators may not emit unregistered shapes."""

from app.models.domain.decoy import DecoyKind, DecoyTemplateId
from app.models.domain.intelligence import PlacementTargetType


class DecoyTemplate:
    def __init__(
        self,
        template_id: DecoyTemplateId,
        decoy_kind: DecoyKind,
        target_types: tuple[PlacementTargetType, ...],
        required_fields: tuple[str, ...],
    ) -> None:
        self.template_id = template_id
        self.decoy_kind = decoy_kind
        self.target_types = target_types
        self.required_fields = required_fields


class DecoyTemplateRegistry:
    def __init__(self) -> None:
        self._templates = (
            DecoyTemplate(
                DecoyTemplateId.SECRET_V1,
                DecoyKind.SECRET,
                (
                    PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE,
                    PlacementTargetType.CI_CD_FILE,
                    PlacementTargetType.CONFIG_FILE,
                    PlacementTargetType.LEGACY_SCRIPT,
                ),
                ("provider_family", "key_name", "fake_value", "authentication_capability"),
            ),
            DecoyTemplate(
                DecoyTemplateId.DOCUMENT_V1,
                DecoyKind.DOCUMENT,
                (
                    PlacementTargetType.ARCHITECTURE_DOCUMENT,
                    PlacementTargetType.DOCUMENTATION_FILE,
                    PlacementTargetType.EXPORTABLE_REPORT,
                    PlacementTargetType.INTERNAL_WIKI_PAGE,
                ),
                ("title", "body", "trace_identifier", "sensitivity_label"),
            ),
            DecoyTemplate(
                DecoyTemplateId.DATABASE_RECORD_V1,
                DecoyKind.DATABASE_RECORD,
                (PlacementTargetType.DATABASE_ROW,),
                ("table_name", "fields", "trace_identifier", "synthetic_data_provenance"),
            ),
        )

    def select(
        self, decoy_kind: DecoyKind, target_type: PlacementTargetType
    ) -> DecoyTemplate | None:
        return next(
            (
                template
                for template in self._templates
                if template.decoy_kind is decoy_kind and target_type in template.target_types
            ),
            None,
        )
