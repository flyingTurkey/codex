# PERS-10 个人界面优化 Design QA

## Comparison target

- Source visual truth:
  - `D:\SRBGData\reports\ui-review\core-pages-20260719T0225Z\01-home-recommended.png`
  - `D:\SRBGData\reports\ui-review\core-pages-20260719T0225Z\02-sources-recommended.png`
  - `D:\SRBGData\reports\ui-review\core-pages-20260719T0225Z\03-detail-recommended.png`
- Browser-rendered implementation:
  - `D:\SRBGData\reports\ui-review\implemented-20260719\01-home-implemented-desktop.png`
  - `D:\SRBGData\reports\ui-review\implemented-20260719\02-sources-implemented-desktop.png`
  - `D:\SRBGData\reports\ui-review\implemented-20260719\03-detail-implemented-desktop.png`
  - `D:\SRBGData\reports\ui-review\implemented-20260719\01-home-implemented-mobile.png`
  - `D:\SRBGData\reports\ui-review\implemented-20260719\03-detail-implemented-mobile.png`
- Viewport/state: desktop comparison artifacts 1673×944; mobile 390×844. The implementation uses the real local Owner session, eight real feed items, 50 real sources, two accepted evidence facts and two Evidence IDs.
- Full-view comparison evidence: each source/implementation pair was opened together in the same visual comparison input.
- Focused-region evidence: the detail comparison made the two evidence panels, their typography, hashes and action controls readable without a separate crop; no additional focused crop was needed.

## Findings

- No remaining P0/P1/P2 findings.
- Fonts and typography: the implementation uses the authoritative Noto Sans SC / Source Han Sans SC stack, 30px desktop headings, tabular numerals, font smoothing and controlled line height. Long Chinese titles wrap without hidden controls or horizontal overflow.
- Spacing and layout rhythm: header, status strip, source overview and evidence panels follow the reference hierarchy. The implementation keeps the existing high-density timeline rather than the mock's shortened sample so all eight real items remain accessible.
- Colors and visual tokens: restrained surface-to-avocado gradients use only repository tokens. Borders, semantic warning colors and focus indicators retain WCAG-oriented contrast.
- Image quality and asset fidelity: these screens contain no photographic or custom raster assets. Existing Iconoir icons remain the sole icon family; no CSS/handmade SVG substitutes were introduced.
- Copy and content: the homepage now identifies the personal research workflow; the source page separates intent, runtime and health; the detail page no longer labels a digital policy as a safety lifecycle and exposes only accepted claims and evidence metadata.
- States and interactions: global active feedback uses 140–180ms tokenized transitions and a 1% press scale. The evidence action was clicked in the in-app browser and opened the correct drawer with the matching accepted claim and full SHA-256. Automatic discovery remains a native, keyboard-accessible disclosure.
- Responsiveness and accessibility: desktop and 390×844 captures show the intended hierarchy; controls retain visible focus and 40px minimum targets. Reduced-motion rules reduce transitions to effectively zero.

## Comparison history

1. Initial pass — blocked:
   - P1: the real digital-policy detail still displayed “安全案例生命周期” and empty accident fields before evidence.
   - P2: automatic discovery dominated the source center first screen.
   - P2: source loading caused hydration mismatch warnings.
2. Fixes:
   - Replaced the legacy safety-only detail framing with “情报详情与证据”.
   - Added two-column accepted-claim and Evidence ID panels; safety-only fields now render only for safety cases.
   - Collapsed automatic discovery behind a native disclosure and moved add-source plus health overview into the first screen.
   - Stabilized source loading across server/client hydration.
3. Post-fix evidence:
   - In-app browser console: no errors or warnings on fresh homepage, source and detail tabs.
   - No horizontal overflow in the measured desktop layouts.
   - Evidence drawer interaction succeeded and projected the selected Evidence ID, locator, full hash and linked accepted claim.
   - `make web-e2e`: 54 passed; `make web-a11y`: 17 passed with zero remaining Axe violations.
   - The final accessibility pass also verifies the source action contrast and the legacy safety-event evidence trigger.

## Follow-up polish

- P3: the mock's compact five-source pilot table is intentionally not copied because the formal product currently contains 50 real sources and must preserve per-source controls.
- P3: the mock's AI-unavailable badge is omitted from the homepage because the current homepage API does not expose a stable AI health contract; the interface does not invent that state.

## Final result

final result: passed
