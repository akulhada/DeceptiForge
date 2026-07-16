"""Thin orchestration over independently testable context layers."""
from app.models.domain.intelligence import OrganizationContextProfile, RepositoryIntelligenceProfile
from app.services.context_engine.assembly import ContextProfileAssembler
from app.services.context_engine.classification import ContextClassifier
from app.services.context_engine.features import ContextFeatureExtractor
from app.services.context_engine.normalization import ContextNormalizer
from app.services.context_engine.scoring import ContextScorer


class ContextEngine:
    def __init__(
        self,
        extractor: ContextFeatureExtractor | None = None,
        normalizer: ContextNormalizer | None = None,
        classifier: ContextClassifier | None = None,
        scorer: ContextScorer | None = None,
        assembler: ContextProfileAssembler | None = None,
    ) -> None:
        self._extractor = extractor or ContextFeatureExtractor()
        self._normalizer = normalizer or ContextNormalizer()
        self._classifier = classifier or ContextClassifier()
        self._scorer = scorer or ContextScorer()
        self._assembler = assembler or ContextProfileAssembler()

    def build(self, profile: RepositoryIntelligenceProfile) -> OrganizationContextProfile:
        context = self._normalizer.normalize(self._extractor.extract(profile))
        classification = self._classifier.classify(context)
        return self._assembler.assemble(
            context, classification, self._scorer.score(context, classification)
        )
