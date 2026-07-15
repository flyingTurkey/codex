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
  'collection-create-request.schema.json': ['CollectionCreateRequest'],
  'collection-patch-request.schema.json': ['CollectionPatchRequest'],
  'collection-summary.schema.json': ['CollectionSummary'],
  'cluster-candidate-view.schema.json': ['ClusterCandidateView'],
  'cluster-decision-request.schema.json': ['ClusterDecisionRequest'],
  'claim-view.schema.json': ['ClaimView'],
  'claim-conflict.schema.json': ['ClaimConflict'],
  'claim-conflict-decision-request.schema.json': ['ClaimConflictDecisionRequest'],
  'claim-conflict-decision-response.schema.json': ['ClaimConflictDecisionResponse'],
  'confirmed-fact.schema.json': ['ConfirmedFact'],
  'create-source-request.schema.json': ['CreateSourceRequest'],
  'cursor-page.schema.json': ['CursorPageDictStrUnionStrIntBoolNoneType'],
  'digital-case-detail.schema.json': [
    'DigitalCaseDetail',
    'DigitalCaseEntity',
    'DigitalCaseOutcome',
  ],
  'digital-case-review-patch.schema.json': [
    'DigitalCaseReviewPatch',
    'DigitalOutcomeAttributionPatch',
  ],
  'daily-draft-request.schema.json': ['DailyDraftRequest'],
  'daily-report.schema.json': ['DailyReport', 'DailyReportItem', 'DailyReportSection'],
  'paper-detail.schema.json': [
    'PaperDetail',
    'PaperAuthor',
    'ResearchInterpretation',
    'SimilarPaper',
  ],
  'technology-product-detail.schema.json': [
    'TechnologyProductDetail',
    'ProductCapability',
    'ProductEngineeringCase',
    'ProductEntity',
  ],
  'product-normalization-candidate.schema.json': ['ProductNormalizationCandidateView'],
  'product-normalization-decision-request.schema.json': ['ProductNormalizationDecisionRequest'],
  'publication-revision-request.schema.json': ['PublicationRevisionRequest'],
  'publication-withdrawal-request.schema.json': ['PublicationWithdrawalRequest'],
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
  'fingerprint-response.schema.json': ['FingerprintResponse'],
  'feedback-request.schema.json': ['FeedbackRequest'],
  'hot-topic-page.schema.json': ['HotTopicPage', 'HotTopicSummary'],
  'fixture-upload-response.schema.json': ['FixtureUploadResponse'],
  'liveness-response.schema.json': ['LivenessResponse'],
  'metric-sample.schema.json': ['MetricSample'],
  'item-summary.schema.json': ['AiAssistance', 'ItemSummary', 'PublicationRevisionState'],
  'item-detail.schema.json': ['ItemDetail'],
  'me-response.schema.json': ['MeResponse'],
  'operations-overview.schema.json': ['OperationsOverview'],
  'pilot-metrics.schema.json': ['PilotMetrics'],
  'problem-details.schema.json': ['ProblemDetails'],
  'readiness-response.schema.json': ['DependencyCheck', 'ReadinessResponse'],
  'replay-request.schema.json': ['ReplayRequest'],
  'replay-result.schema.json': ['ReplayResult'],
  'score-override-request.schema.json': ['ScoreOverrideRequest'],
  'score-summary.schema.json': [
    'ScoreSummary',
    'ScoreDimensionSummary',
    'ScoreFeature',
  ],
  'save-item-request.schema.json': ['SaveItemRequest'],
  'search-context.schema.json': ['SearchContext'],
  'review-decision-request.schema.json': ['ReviewDecisionRequest'],
  'review-decision-response.schema.json': ['ReviewDecisionResponse'],
  'review-candidate-decision-request.schema.json': ['ReviewCandidateDecisionRequest'],
  'review-task-detail.schema.json': ['ReviewTaskDetail'],
  'review-task-summary.schema.json': ['ReviewTaskSummary'],
  'source-action-request.schema.json': ['SourceActionRequest'],
  'source-comparison.schema.json': ['SourceComparison', 'SourceComparisonEntry'],
  'source-detail.schema.json': ['SourceDetail'],
  'source-onboarding-submission.schema.json': ['SourceOnboardingSubmission'],
  'source-policy-submission.schema.json': ['SourcePolicySubmission'],
  'source-summary.schema.json': ['SourceSummary'],
  'source-transition-request.schema.json': ['SourceTransitionRequest'],
  'type-summary.schema.json': [
    'TypeSummary',
    'SafetyRegulationTypeSummary',
    'SafetyCaseTypeSummary',
    'DigitalCaseTypeSummary',
    'PaperTypeSummary',
    'SoftwareProductTypeSummary',
    'IotProductTypeSummary',
    'LowAltitudeEquipmentTypeSummary',
    'AiEquipmentTypeSummary',
    'RelevanceFactor',
    'RelevanceSummary',
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
    ignoreMinAndMaxItems: true,
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
