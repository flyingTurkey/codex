# Issue tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues at
`flyingTurkey/codex`. Use the `gh` CLI for all operations.

## Conventions

- Create: `gh issue create --repo flyingTurkey/codex --title "..." --body-file <file>`
- Read: `gh issue view <number> --repo flyingTurkey/codex --comments`
- List: `gh issue list --repo flyingTurkey/codex --state open --json number,title,body,labels,comments`
- Comment: `gh issue comment <number> --repo flyingTurkey/codex --body "..."`
- Add a label: `gh issue edit <number> --repo flyingTurkey/codex --add-label "..."`
- Remove a label: `gh issue edit <number> --repo flyingTurkey/codex --remove-label "..."`
- Close: `gh issue close <number> --repo flyingTurkey/codex --comment "..."`

When working inside this clone, `gh` may infer the repository from the
configured `origin`. Explicit `--repo flyingTurkey/codex` remains acceptable.

## Pull requests as a triage surface

**PRs as a request surface: no.**

Pull requests are not treated as incoming feature requests by default.

GitHub shares one number space across issues and pull requests. If a bare
reference such as `#42` is ambiguous, try `gh pr view 42` and then
`gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue in `flyingTurkey/codex`.

## When a skill says "fetch the relevant ticket"

Run:

`gh issue view <number> --repo flyingTurkey/codex --comments`

## Wayfinding operations

The `/wayfinder` skill represents a large effort as one map issue with child
issues:

- Map: one issue labelled `wayfinder:map`.
- Child: a linked sub-issue labelled `wayfinder:<type>`.
- Types: `research`, `prototype`, `grilling`, or `task`.
- Blocking: prefer GitHub native issue dependencies. If unavailable, place
  `Blocked by: #<number>` near the top of the child issue.
- Frontier: choose the first open, unblocked, and unassigned child.
- Claim: assign the issue to the current user.
- Resolve: comment with the answer, close the child, and add a context pointer
  to the map's Decisions-so-far section.
