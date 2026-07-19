"""Qualification decisions that prevent extraction and publication side effects."""

from srbg_api.ai_pipeline.contracts import ClassificationOutput

AUTO_PASS_CONFIDENCE = 0.90


def classification_allows_extraction(output: ClassificationOutput) -> bool:
    return (
        output.direct_relevance == "RELEVANT"
        and output.confidence >= AUTO_PASS_CONFIDENCE
        and not output.needs_human_review
        and output.primary_type is not None
    )
