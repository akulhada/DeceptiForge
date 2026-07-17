"""Deterministic payload generation for the approved MVP templates."""

from hashlib import sha256

from app.models.domain.decoy import (
    DecoyField,
    GeneratedDatabaseRecord,
    GeneratedDocument,
    GeneratedSecret,
)
from app.models.domain.intelligence import OrganizationContextProfile, PlacementRecommendation


class PayloadGenerators:
    def generate(
        self,
        recommendation: PlacementRecommendation,
        context: OrganizationContextProfile,
        trace_identifier: str,
    ) -> GeneratedSecret | GeneratedDocument | GeneratedDatabaseRecord:
        vocabulary = self._vocabulary(context)
        digest = sha256(trace_identifier.encode()).hexdigest()
        match recommendation.future_asset_type_recommendation.value:
            case "secret":
                key_name = f"{vocabulary.upper()}_SERVICE_TOKEN"
                return GeneratedSecret(
                    provider_family="internal-service-token",
                    key_name=key_name,
                    fake_value=f"dfg_inert_{digest[:40]}",
                    entropy_profile="sha256-derived-40-hex",
                    naming_rationale=f"Uses the observed {vocabulary.upper()} service vocabulary.",
                    target_file_style="upper_snake_case",
                    rotation_recommendation="Rotate on access or every 90 days; value is inert.",
                )
            case "document":
                title = f"{vocabulary.title()} Deployment Runbook"
                return GeneratedDocument(
                    title=title,
                    body=(
                        f"Internal note: verify {vocabulary} deployment handoff before release. "
                        f"Reference: {trace_identifier}."
                    ),
                    target_document_type="runbook",
                    sensitivity_label="internal",
                    trace_identifier=trace_identifier,
                )
            case "database_record":
                return GeneratedDatabaseRecord(
                    table_name=f"{vocabulary}_customers",
                    entity_type="enterprise_customer",
                    fields=(
                        DecoyField(
                            name="external_reference",
                            data_type="string",
                            display_value=trace_identifier,
                        ),
                        DecoyField(
                            name="organization_name",
                            data_type="string",
                            display_value=f"Northstar {vocabulary.title()} Systems",
                        ),
                        DecoyField(
                            name="contact_email",
                            data_type="string",
                            display_value="contact@invalid.example",
                        ),
                    ),
                    relationship_placeholders=("account_manager_id:synthetic",),
                    trace_identifier=trace_identifier,
                    export_detection_fingerprint=digest[:24],
                )
        raise ValueError("Unsupported decoy kind")

    @staticmethod
    def _vocabulary(context: OrganizationContextProfile) -> str:
        if context.primary_technical_vocabulary:
            return context.primary_technical_vocabulary[0].value.replace("-", "_")
        return "platform"
