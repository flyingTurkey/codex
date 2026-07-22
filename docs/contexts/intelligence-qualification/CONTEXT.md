# Intelligence Qualification

Intelligence Qualification decides whether newly acquired material is directly useful civil-engineering intelligence.

## Language

**DirectRelevance**:
The material centers an in-scope engineering object or construction equipment and contains a substantive new fact affecting its planning, design, construction, operation, maintenance, safety or digitalization.
_Avoid_: Keyword match

**PrimaryType**:
Exactly one of `DIGITAL_TRANSFORMATION`, `SAFETY_INTELLIGENCE` or `INDUSTRY_UPDATE` assigned to a relevant Event.
_Avoid_: Channel, multiple categories

**EngineeringObject**:
One of highway, railway, bridge, tunnel, building, mining, municipal, water conservancy, port/waterway, airport or energy engineering.
_Avoid_: Industry keyword

**SpecialtyFacet**:
The `TUNNEL_GAS_MONITORING` cross-cutting attribute; it does not replace an EngineeringObject or PrimaryType.
_Avoid_: Primary category

**EquipmentDomain**:
The `CONSTRUCTION_MACHINERY` attribute for equipment directly used in the in-scope engineering lifecycle.
_Avoid_: General manufacturing

**IndustryUpdate**:
A relevant engineering development whose central new fact is neither primarily a digital transformation nor primarily safety intelligence.
_Avoid_: General news, popularity

**QualificationReviewCase**:
A historical compatibility case. New autonomous runs do not create one for low confidence, classification failure, primary-type conflict or filtering.
_Avoid_: Autonomous decision, operational exception

**QualificationPolicy**:
An immutable identity binding global rules, SourceStream policy, model, Prompt, output Schema, code version and a server-computed digest for one replayable qualification behavior.
_Avoid_: Mutable runtime flags, `OWNER_OVERRIDE_GO`

**AutomatedDisposition**:
The server-owned outcome/control vocabulary: `AUTO_ACCEPTED`, `AUTO_FILTERED`, `TECHNICAL_RETRY`, `TECHNICAL_FAILED`, `SAFETY_HOLD` or `OWNER_SUPPRESSED`.
_Avoid_: Publication status, model output authority

**BoundedSemanticReadjudication**:
The single permitted second semantic classification when deterministic rules conflict with a valid model candidate. A remaining conflict becomes `AUTO_FILTERED` and creates no Owner semantic task.
_Avoid_: Retry loop, confidence threshold

**OwnerException**:
An operational technical exception or a separately overrideable/non-overrideable safety exception. It is not a semantic classification queue.
_Avoid_: Generic review case

**FeedSuppressionRule**:
An append-only Owner preference or classification-error feedback fact scoped to an Event, type, domain axis, source or custom topic.
_Avoid_: Publication denial, source deauthorization

**PolicyEvaluation**:
An aggregate-only offline replay or shadow evaluation. It never authorizes production and never exposes case-level private evidence.
_Avoid_: Production GO, benchmark export

## Production flow

For a currently authorized SourceStream, raw content and its document version are persisted before qualification. `AUTO_FILTERED` stops before Item/Event and reader projection creation. `AUTO_ACCEPTED` only authorizes continued evidence processing; it is not itself publication. Accepted claims, bidirectional evidence and SourceExcerpt are revalidated by `PublicationService`, which alone writes Feed, search, hotspot and Event projections. A replacement document version invalidates old claims/projections and is adjudicated under the current immutable policy bundle.

SourceAdmission is independent from document qualification. It pauses on hard public-network/access restrictions and explicit robots, terms or copyright prohibitions. Missing legal metadata, soft-yield observations and qualification leakage permit bounded collection; leakage informs policy iteration instead of source authorization. HUMAN_OWNER Gold and model output never authorize a source.
