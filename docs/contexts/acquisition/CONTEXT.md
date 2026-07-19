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
A fail-closed decision that a Source and SourceStream satisfy public-network safety, robots, terms, copyright, access, quality and operating limits.
_Avoid_: Enable switch

**SourceExit**:
A pause or retirement caused by a hard-gate failure or repeated soft-quality failure.
_Avoid_: Fetch error
