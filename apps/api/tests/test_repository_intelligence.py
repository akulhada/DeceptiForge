from app.models.domain.intelligence import NamingCategory, NamingStyle, Separator
from app.services.repository_intelligence.naming import (
    NamingCorpus,
    NamingPatternInferenceEngine,
    NamingSourceFile,
)
from app.services.repository_intelligence.scanner import LocalRepositoryScanner


def test_inferrs_repository_naming_conventions() -> None:
    profile = NamingPatternInferenceEngine().infer(
        NamingCorpus(
            file_paths=("src/payment-service/billing.controller.ts", "workers/payment_service.py"),
            text_fragments=(
                "PAYMENT_SERVICE_KEY AUTH_JWT_SECRET CREATE TABLE customer_profiles (id uuid)",
            ),
            service_names=("billing-service", "invoice-worker"),
            api_names=("/v1/customer-profiles/{id}",),
        )
    )

    assert any(
        item.category is NamingCategory.ENVIRONMENT_VARIABLE
        and item.style is NamingStyle.SCREAMING_SNAKE
        for item in profile.naming_style
    )
    assert any(
        item.category is NamingCategory.SERVICE and item.separator is Separator.HYPHEN
        for item in profile.naming_style
    )
    assert "payment" in profile.common_prefixes
    assert profile.confidence > 0


def test_extracts_python_routes_and_ignores_generated_paths() -> None:
    profile = NamingPatternInferenceEngine().infer(
        NamingCorpus(
            file_paths=("node_modules/foo.js",),
            source_files=(
                NamingSourceFile(path="routes.py", content='router.get("/v1/invoice-items")'),
            ),
        )
    )

    assert any(
        item.category is NamingCategory.API and item.style is NamingStyle.KEBAB
        for item in profile.naming_style
    )
    assert not any(
        "node_modules" in sample for item in profile.naming_style for sample in item.samples
    )


def test_scans_a_local_repository_without_retaining_source_content(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "payment-service.py").write_text(
        'API_KEY = "not-a-real-key"\nrouter.get("/v1/customer-profiles")', encoding="utf-8"
    )
    (tmp_path / ".env.example").write_text("PAYMENT_DB_HOST=example", encoding="utf-8")

    profile = LocalRepositoryScanner().scan(tmp_path)

    assert profile.file_count == 2
    assert profile.naming_profile is not None
    assert profile.secret_locations[0].path == ".env.example"
    assert "not-a-real-key" not in profile.model_dump_json()
