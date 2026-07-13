# Design QA

- source visual truth path: `../../assets/ui/references/selected-concept-01.png`
- implementation: `prototype/selected-feed/`
- target viewport: 1488×1058 desktop; 1024×768 compact; 768px reading layout
- state: 今日精选 / 全部 / 默认筛选
- build evidence: `npm run build` passed
- browser-rendered implementation screenshot: unavailable
- primary interactions tested in browser: unavailable
- console errors checked in browser: unavailable
- full-view comparison evidence: blocked because the available browser rejected the local preview URL
- focused region comparison evidence: blocked for the same reason

**Findings**

- [P1] Browser-rendered comparison is unavailable.
  - Location: full prototype.
  - Evidence: source image can be opened, production build passes, but the browser security policy rejected the local preview URL before capture.
  - Impact: visual fidelity, overflow and interaction polish cannot be certified from rendered evidence.
  - Fix: run the supplied visual regression and interaction checks in the target repository/browser during round 00A; compare the same viewport against `selected-concept-01.png`.

**Implementation Checklist**

- Capture 1488×1058 or nearest 1440×900 default state.
- Capture 1024×768 compact-sidebar state.
- Test search, category Tab, verified filter, bookmark, empty-state reset and evidence drawer.
- Check browser console and axe.
- Compare source and implementation in one visual input; resolve P0/P1/P2 before production handoff.

**Follow-up Polish**

- Confirm installed Chinese font rendering on the enterprise desktop image.
- Confirm official Logo spacing after brand assets are supplied.

final result: blocked
