import { readdir, mkdir, rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { compileFromFile } from 'json-schema-to-typescript'

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const schemaDir = join(packageRoot, 'generated', 'json-schema')
const outputPath = join(packageRoot, 'generated', 'types', 'index.d.ts')
const schemaFiles = (await readdir(schemaDir))
  .filter((file) => file.endsWith('.json'))
  .sort()

const publicExports = {
  'claim-view.schema.json': ['ClaimView'],
  'claim-conflict.schema.json': ['ClaimConflict'],
  'claim-conflict-decision-request.schema.json': ['ClaimConflictDecisionRequest'],
  'claim-conflict-decision-response.schema.json': ['ClaimConflictDecisionResponse'],
  'confirmed-fact.schema.json': ['ConfirmedFact'],
  'create-source-request.schema.json': ['CreateSourceRequest'],
  'cursor-page.schema.json': ['CursorPageDictStrUnionStrIntBoolNoneType'],
  'document-detail.schema.json': ['DocumentDetail'],
  'document-page-view.schema.json': ['DocumentPageView'],
  'evidence-view.schema.json': ['EvidenceView'],
  'event-candidate-generation-response.schema.json': ['EventCandidateGenerationResponse'],
  'event-detail.schema.json': ['EventDetail'],
  'event-item.schema.json': ['EventItem'],
  'event-relation-view.schema.json': ['EventRelationView'],
  'event-timeline.schema.json': ['EventTimeline'],
  'feed-notice.schema.json': ['FeedNotice'],
  'feed-page.schema.json': ['FeedPage'],
  'fixture-upload-response.schema.json': ['FixtureUploadResponse'],
  'liveness-response.schema.json': ['LivenessResponse'],
  'item-summary.schema.json': ['ItemSummary'],
  'item-detail.schema.json': ['ItemDetail'],
  'me-response.schema.json': ['MeResponse'],
  'problem-details.schema.json': ['ProblemDetails'],
  'readiness-response.schema.json': ['DependencyCheck', 'ReadinessResponse'],
  'review-decision-request.schema.json': ['ReviewDecisionRequest'],
  'review-decision-response.schema.json': ['ReviewDecisionResponse'],
  'review-candidate-decision-request.schema.json': ['ReviewCandidateDecisionRequest'],
  'review-task-detail.schema.json': ['ReviewTaskDetail'],
  'review-task-summary.schema.json': ['ReviewTaskSummary'],
  'source-action-request.schema.json': ['SourceActionRequest'],
  'source-detail.schema.json': ['SourceDetail'],
  'source-onboarding-submission.schema.json': ['SourceOnboardingSubmission'],
  'source-policy-submission.schema.json': ['SourcePolicySubmission'],
  'source-summary.schema.json': ['SourceSummary'],
  'source-transition-request.schema.json': ['SourceTransitionRequest'],
  'type-summary.schema.json': [
    'TypeSummary',
    'SafetyRegulationTypeSummary',
    'SafetyCaseTypeSummary',
  ],
  'unverified-fact.schema.json': ['UnverifiedFact'],
  'version-diff-response.schema.json': ['VersionDiffResponse'],
  'version-change-escalation-request.schema.json': ['VersionChangeEscalationRequest'],
  'version-response.schema.json': ['VersionResponse'],
  'version-timeline-response.schema.json': ['VersionTimelineResponse'],
}

await mkdir(dirname(outputPath), { recursive: true })
const staleDeclarations = (await readdir(dirname(outputPath)))
  .filter((file) => file.endsWith('.d.ts'))
for (const staleDeclaration of staleDeclarations) {
  await rm(join(dirname(outputPath), staleDeclaration))
}

const reexports = []
for (const schemaFile of schemaFiles) {
  const outputFile = schemaFile.replace(/\.json$/, '.d.ts')
  const declaration = await compileFromFile(join(schemaDir, schemaFile), {
    bannerComment: '',
    style: { semi: false, singleQuote: true },
    unknownAny: false,
  })
  await writeFile(join(dirname(outputPath), outputFile), declaration, 'utf8')
  const exportedNames = publicExports[schemaFile]
  if (!exportedNames) {
    throw new Error(`No public export mapping for ${schemaFile}`)
  }
  for (const exportedName of exportedNames) {
    reexports.push(
      `export type { ${exportedName} } from './${outputFile.replace(/\.d\.ts$/, '')}'`,
    )
  }
}

const banner = '// Generated from canonical Pydantic contracts. Do not edit directly.\n\n'
await writeFile(outputPath, banner + reexports.join('\n') + '\n', 'utf8')
