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
A non-public Owner case created for low confidence, classification failure, primary-type tie or restricted risk.
_Avoid_: Draft Event
