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

**RuntimeAuthorization**:
The current server-controlled right to consume a model result for one document version after source, document, safety, execution-domain and budget gates are satisfied.
_Avoid_: Configured, enabled

**RealSchemaSuccess**:
A real approved provider and model call whose output passes the local step Schema; probes, mocks, network reachability and configuration do not establish it.
_Avoid_: Heartbeat, configured

**AIAvailability**:
The capability state supported by fresh runtime health and a RealSchemaSuccess inside the required time window; it is distinct from an individual AISummary and SummaryState.
_Avoid_: Configured, runtime heartbeat

**DurableContentHandoff**:
A recoverable responsibility record for handing acquired content to the AI pipeline. Its terminality means the handoff is closed, not that AI succeeded, a claim was accepted, an Event exists or publication succeeded.
_Avoid_: AISummary, publication result
