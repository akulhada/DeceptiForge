from app.models.domain.intelligence import NamingCategory, NamingStyle, Separator
from app.services.repository_intelligence.analyzers import (
    AnalyzerContribution,
    CicdAnalyzer,
    LanguageAnalyzer,
)
from app.services.repository_intelligence.evidence import FileEntry, RepositoryEvidence
from app.services.repository_intelligence.naming import (
    NamingCorpus,
    NamingPatternInferenceEngine,
    NamingSourceFile,
)
from app.services.repository_intelligence.scanner import LocalRepositoryScanner


def _evidence(*files: FileEntry, fragments: tuple[str, ...] = ()) -> RepositoryEvidence:
    counts: dict[str, int] = {}
    for entry in files:
        counts[entry.suffix] = counts.get(entry.suffix, 0) + 1
    return RepositoryEvidence(
        root_path="/repo",
        repository_name="repo",
        is_git_repository=True,
        files=files,
        extension_counts=counts,
        text_fragments=fragments,
        truncated=False,
    )


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


def test_detects_cicd_docker_and_terraform_in_one_pass(tmp_path) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12", encoding="utf-8")
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "main.tf").write_text('provider "aws" {}', encoding="utf-8")

    profile = LocalRepositoryScanner().scan(tmp_path)

    assert [item.name for item in profile.cicd] == ["GitHub Actions"]
    assert profile.infrastructure.docker_files == ("Dockerfile",)
    assert profile.infrastructure.terraform_files == ("infra/main.tf",)
    assert any(item.name == "AWS" for item in profile.cloud_providers)


def test_analyzers_are_independently_unit_testable() -> None:
    evidence = _evidence(
        FileEntry(path=".github/workflows/ci.yml", name="ci.yml", suffix=".yml"),
        FileEntry(path="Jenkinsfile", name="Jenkinsfile", suffix=""),
        FileEntry(path="app/main.py", name="main.py", suffix=".py"),
    )

    cicd = CicdAnalyzer().analyze(evidence)
    languages = LanguageAnalyzer().analyze(evidence)

    assert {item.name for item in cicd.cicd} == {"GitHub Actions", "Jenkins"}
    assert cicd.confidence is not None and cicd.confidence.analyzer == "cicd"
    assert [item.name for item in languages.languages] == ["Python"]


def test_scanner_pipeline_is_extensible_with_a_custom_analyzer(tmp_path) -> None:
    (tmp_path / "app.py").write_text("print('x')", encoding="utf-8")

    class TaggingAnalyzer:
        name = "tagging"

        def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
            from app.models.domain.organization import TechnologyEvidence

            return AnalyzerContribution(
                mcp_configurations=(
                    TechnologyEvidence(name="custom-tag", confidence=1.0, evidence=("test",)),
                )
            )

    profile = LocalRepositoryScanner(analyzers=(TaggingAnalyzer(),)).scan(tmp_path)

    assert [item.name for item in profile.mcp_configurations] == ["custom-tag"]
    assert profile.languages == ()
