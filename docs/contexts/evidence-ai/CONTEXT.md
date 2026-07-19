# Evidence & AI

Evidence & AI separates source-supported facts from model-authored interpretation.

## Language

**AcceptedClaim**:
A currently active factual assertion with bidirectional references to evidence in the same source version.
_Avoid_: Model answer

**SourceExcerpt**:
One continuous source passage of at most 500 Chinese characters selected from evidence supporting active AcceptedClaims, plus only minimal surrounding context.
_Avoid_: Abstract, AI summary

**AISummary**:
A 300–500 Chinese-character interpretation of what happened, engineering impact, and limits or follow-up, whose factual paragraphs cite AcceptedClaims and whose judgments are explicitly separate.
_Avoid_: Evidence fact, source excerpt

**ClaimBasis**:
One of manufacturer claim, research conclusion, project first-party record, independent verification or authority finding.
_Avoid_: Confidence

**SummaryState**:
One of not generated, processing, temporarily unavailable, schema rejected, insufficient evidence, succeeded or stale.
_Avoid_: Enabled

**AuthorityReservedClaim**:
An accident cause, responsibility, penalty conclusion or legal effect that can be accepted only from the competent authority's original material.
_Avoid_: Inference
