# Acquisition

Acquisition preserves compliant source material before any relevance or publication decision.

## Language

**Source**:
An institution accountable for content provenance and admission quality; multiple site sections do not become multiple Sources.
_Avoid_: Channel, column

**SourceStream**:
A bounded API, RSS, sitemap, list page or other collection path operated by one Source.
_Avoid_: Source

**RawResponse**:
The immutable bytes, response metadata and content hash saved before parsing.
_Avoid_: Article

**SourceAdmission**:
A server-owned decision that a Source and SourceStream satisfy public-network safety, access, explicit legal restrictions and operating limits. Explicitly blocked or restricted robots, terms or copyright evidence fails closed; genuinely absent or unknown legal metadata permits only bounded collection and remains observable. Its assessment fact is append-only and cannot itself start a source.
_Avoid_: Enable switch

**SourceExit**:
A pause or retirement caused by a hard-gate failure or repeated soft-quality failure.
_Avoid_: Fetch error

**TrustedDnsResolution**:
An application-owned RFC 8484 lookup used to obtain the real public A/AAAA
set before an acquisition socket is opened. Operating-system and VPN DNS are
not authority because transparent VPNs may return synthetic addresses. The
configured DoH endpoint is authenticated with TLS and a public bootstrap IP;
failure never falls back to system DNS. The existing SSRF policy still rejects
non-public answers, pins the validated set for the request, revalidates every
redirect, and requires the connected peer to match.
_Avoid_: VPN DNS, fake-IP allowlist

**ContentRelevance**:
A SourceStream research assessment of `DIRECT` or `FILTERED`; it describes the stream's expected filtering burden and never qualifies an individual document.
_Avoid_: DirectRelevance, publication eligibility

**StreamReadiness**:
One of `BOUNDED`, `CANDIDATE`, `SAMPLE` or `MANUAL_ONLY`, expressing whether a stable public collection boundary has been established without implying SourceAdmission.
_Avoid_: Enabled, admitted

**JurisdictionRole**:
Either `CN_PRIMARY` for a candidate Chinese fact source or `FOREIGN_SHADOW` for reference-only foreign material with no Chinese legal effect.
_Avoid_: Authority level

**SourceResearchDisposition**:
One of `ADMISSION_READY`, `BOUNDARY_DISCOVERY` or `MANUAL_SHADOW`; it routes follow-up research and never grants collection or runtime authority.
_Avoid_: SourceAdmission, rollout status

**SourceCoverageMatrix**:
A dated assessment of source evidence for an explicit subset of EngineeringObjects and facets; it neither defines the product domain nor grants DirectRelevance or SourceAdmission.
_Avoid_: Domain boundary, admitted roster

**Policy-bound content handoff**:
The atomic transition that creates a LIVE pipeline run with the active
`policy_bundle_id`. Acquisition supplies immutable content and SourceStream
policy identity but does not choose a Challenger, promote a policy, or grant
publication.
_Avoid_: Re-reading the active policy during a callback
