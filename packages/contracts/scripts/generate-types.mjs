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
  'ai-summary-v2.schema.json': ['AiSummaryV2', 'AiSummaryStatusV2'],
  'event-appendix-v2.schema.json': ['EventAppendixV2'],
  'event-full-projection-v2.schema.json': [
    'EventFullProjectionV2',
    'PrimaryIntelligenceType',
    'EngineeringObject',
    'SpecialtyFacet',
    'EquipmentFacet',
    'ClaimBasisV2',
  ],
  'event-metadata-projection-v2.schema.json': ['EventMetadataProjectionV2'],
  'feed-page-v2.schema.json': ['FeedPageV2'],
  'review-decision-command-v2.schema.json': ['ReviewDecisionCommandV2'],
  'review-decision-receipt-v2.schema.json': ['ReviewDecisionReceiptV2'],
  'review-case-v2.schema.json': ['ReviewCaseV2'],
  'quarantine-projection-v2.schema.json': ['QuarantineProjectionV2'],
  'hotspot-candidate-v2.schema.json': ['HotspotCandidateV2'],
  'collection-create-request.schema.json': ['CollectionCreateRequest'],
  'collection-patch-request.schema.json': ['CollectionPatchRequest'],
  'collection-summary.schema.json': ['CollectionSummary'],
  'connector-config-preview.schema.json': ['ConnectorConfigPreview'],
  'connector-config-preview-request.schema.json': ['ConnectorConfigPreviewRequest'],
  'connector-config-request.schema.json': ['ConnectorConfigRequest'],
  'connector-config-version.schema.json': ['ConnectorConfigVersionView'],
  'connector-definition.schema.json': ['ConnectorDefinitionView', 'ConnectorType'],
  'source-assessment-submission.schema.json': [
    'SourceAssessmentSubmission',
    'SourceAuthorityAssessment',
    'SourceIndependenceAssessment',
    'AuthorityLevel',
    'SourceIndependenceLevel',
  ],
  'source-governance-metadata-update.schema.json': ['SourceGovernanceMetadataUpdate'],
  'cluster-candidate-view.schema.json': ['ClusterCandidateView'],
  'cluster-decision-request.schema.json': ['ClusterDecisionRequest'],
  'automatic-relationship-view.schema.json': ['AutomaticRelationshipView', 'AutomaticRelationshipKind'],
  'owner-relationship-correction-request.schema.json': [
    'OwnerRelationshipCorrectionRequest',
    'EventSplitAllocation',
  ],
  'owner-relationship-correction-response.schema.json': ['OwnerRelationshipCorrectionResponse'],
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
  'published-event-summary-v1.schema.json': ['PublishedEventSummaryV1'],
  'published-event-detail-v1.schema.json': [
    'PublishedEventDetailV1',
    'PublishedClaimV1',
    'PublishedEvidenceReferenceV1',
  ],
  'document-detail.schema.json': ['DocumentDetail'],
  'document-page-view.schema.json': ['DocumentPageView'],
  'evidence-view.schema.json': ['EvidenceView'],
  'event-candidate-generation-response.schema.json': ['EventCandidateGenerationResponse'],
  'event-detail.schema.json': ['EventDetail'],
  'event-automatic-result-view.schema.json': ['EventAutomaticResultView'],
  'event-item.schema.json': ['EventItem'],
  'event-relation-view.schema.json': ['EventRelationView'],
  'event-timeline.schema.json': ['EventTimeline'],
  'feed-notice.schema.json': ['FeedNotice'],
  'feed-page.schema.json': ['FeedPage'],
  'fingerprint-response.schema.json': ['FingerprintResponse'],
  'feedback-request.schema.json': ['FeedbackRequest'],
  'gold-annotation-request.schema.json': ['GoldAnnotationRequest'],
  'gold-annotation-view.schema.json': ['GoldAnnotationView'],
  'gold-arbitration-packet.schema.json': ['GoldArbitrationPacket'],
  'gold-arbitration-request.schema.json': ['GoldArbitrationRequest'],
  'gold-release-request.schema.json': ['GoldReleaseRequest'],
  'gold-release-view.schema.json': ['GoldReleaseView'],
  'gold-task-create-request.schema.json': ['GoldTaskCreateRequest'],
  'gold-task-view.schema.json': ['GoldTaskView'],
  'hot-topic-page.schema.json': ['HotTopicPage', 'HotTopicSummary'],
  'fixture-upload-response.schema.json': ['FixtureUploadResponse'],
  'liveness-response.schema.json': ['LivenessResponse'],
  'metric-sample.schema.json': ['MetricSample'],
  'item-summary.schema.json': ['AiAssistance', 'ItemSummary', 'PublicationRevisionState'],
  'item-detail.schema.json': ['ItemDetail'],
  'me-response.schema.json': ['MeResponse'],
  'personal-source-patch-request.schema.json': ['PersonalSourcePatchRequest'],
  'personal-source-create-request.schema.json': ['PersonalSourceCreateRequest'],
  'personal-source-reprobe-request.schema.json': ['PersonalSourceReprobeRequest'],
  'personal-source-stream-view.schema.json': [
    'PersonalSourceStreamView',
    'PersonalSourceStreamType',
    'PersonalSourceStreamStatus',
  ],
  'stream-probe-run-view.schema.json': [
    'StreamProbeRunView',
    'PersonalSourceInputKind',
    'PersonalSourceProbeStatus',
  ],
  'personal-source-view.schema.json': [
    'PersonalSourceRuntimeState',
    'PersonalSourceView',
    'SourceProfileSummaryView',
  ],
  'personal-source-activity-page.schema.json': [
    'PersonalSourceActivityPage',
    'PersonalSourceActivityItemView',
    'PersonalSourceRunSummaryView',
  ],
  'source-profile-model-output.schema.json': [
    'SourceProfileCandidate',
    'SourceProfileModelOutput',
  ],
  'source-profile-override-request.schema.json': ['SourceProfileOverrideRequest'],
  'source-profile-view.schema.json': [
    'SourceProfileBasis',
    'SourceProfileEvidenceView',
    'SourceProfileFieldExplanation',
    'SourceProfileStatus',
    'SourceProfileValues',
    'SourceProfileView',
  ],
  'operations-overview.schema.json': ['OperationsOverview'],
  'operator-task-complete-request.schema.json': ['OperatorTaskCompleteRequest'],
  'operator-task-create-request.schema.json': ['OperatorTaskCreateRequest'],
  'operator-task-view.schema.json': ['OperatorTaskView'],
  'operator-work-session-correction-request.schema.json': [
    'OperatorWorkSessionCorrectionRequest',
  ],
  'operator-work-session-heartbeat-request.schema.json': [
    'OperatorWorkSessionHeartbeatRequest',
  ],
  'operator-work-session-start.schema.json': ['OperatorWorkSessionStart'],
  'operator-work-session-stop-request.schema.json': ['OperatorWorkSessionStopRequest'],
  'operator-work-session-view.schema.json': ['OperatorWorkSessionView'],
  'pilot-metrics.schema.json': ['PilotMetrics'],
  'pilot-source-resume-request.schema.json': ['PilotSourceResumeRequest'],
  'pilot-window-complete-request.schema.json': ['PilotWindowCompleteRequest'],
  'pilot-window-create-request.schema.json': ['PilotWindowCreateRequest'],
  'pilot-window-start-request.schema.json': ['PilotWindowStartRequest'],
  'pilot-window-view.schema.json': ['PilotWindowView'],
  'problem-details.schema.json': ['ProblemDetails'],
  'readiness-response.schema.json': ['DependencyCheck', 'ReadinessResponse'],
  'replay-request.schema.json': ['ReplayRequest'],
  'replay-result.schema.json': ['ReplayResult'],
  'replay-task-view.schema.json': ['ReplayTaskView'],
  'fetch-schedule-update.schema.json': ['FetchScheduleUpdate'],
  'fetch-schedule-view.schema.json': [
    'FetchScheduleView',
    'FetchScheduleStatus',
    'CircuitState',
  ],
  'source-health-view.schema.json': ['SourceHealthView', 'SourceAnomalyView'],
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
  'source-attention-page.schema.json': ['SourceAttentionPage', 'SourceAttentionItem'],
  'source-audit-event.schema.json': ['SourceAuditEventView'],
  'source-candidate-batch-decision-request.schema.json': [
    'SourceCandidateBatchDecisionRequest',
  ],
  'source-candidate-batch-decision-result.schema.json': [
    'SourceCandidateBatchDecisionResult',
    'SourceCandidateDecisionItemResult',
    'SourceCandidateDecisionItemOutcome',
  ],
  'source-candidate-create-request.schema.json': ['SourceCandidateCreateRequest'],
  'source-candidate-decision-request.schema.json': [
    'SourceCandidateDecisionRequest',
    'SourceCandidateDecision',
  ],
  'source-candidate-decision-result.schema.json': ['SourceCandidateDecisionResult'],
  'source-candidate-detail.schema.json': ['SourceCandidateDetail'],
  'source-candidate-page.schema.json': [
    'SourceCandidatePage',
    'SourceCandidateSummary',
    'QualificationBundleView',
    'QualificationCheckView',
    'SourceCandidateAction',
    'SourceCandidateStatus',
    'SourceContentDomain',
    'SourceIndustry',
    'DiscoveryChannel',
    'QualificationCheckLevel',
    'QualificationVerdict',
    'EvidenceCapturePolicy',
    'StoragePolicy',
  ],
  'source-candidate-qualification-request.schema.json': [
    'SourceCandidateQualificationRequest',
  ],
  'source-comparison.schema.json': ['SourceComparison', 'SourceComparisonEntry'],
  'source-coverage-matrix.schema.json': ['SourceCoverageMatrix', 'SourceCoverageCell'],
  'source-detail.schema.json': ['SourceDetail'],
  'source-lifecycle-action-request.schema.json': ['SourceLifecycleActionRequest'],
  'source-lifecycle-event.schema.json': ['SourceLifecycleEventView'],
  'source-onboarding-submission.schema.json': ['SourceOnboardingSubmission'],
  'source-policy-decision-request.schema.json': ['SourcePolicyDecisionRequest'],
  'source-policy-submission.schema.json': ['SourcePolicySubmission'],
  'source-policy-v2-submission.schema.json': [
    'SourcePolicyV2Submission',
    'ReviewEvidence',
    'SourceFetchPolicy',
    'SourceRetentionPolicy',
    'SourceSloPolicy',
  ],
  'source-policy-version.schema.json': ['SourcePolicyVersionView'],
  'source-production-approval-request.schema.json': ['SourceProductionApprovalRequest'],
  'source-summary.schema.json': [
    'SourceSummary',
    'SourceLifecycleAction',
    'SourceLifecycleState',
    'RuntimeAuthorization',
  ],
  'source-stream-page.schema.json': [
    'SourceStreamPage',
    'SourceStreamView',
    'SourceStreamAction',
    'SourceStreamStatus',
  ],
  'source-trial-run-request.schema.json': ['SourceTrialRunRequest'],
  'source-trial-quality-summary.schema.json': ['SourceTrialQualitySummary'],
  'source-trial-run.schema.json': [
    'SourceTrialRunView',
    'SourceTrialKind',
    'SourceTrialRunStatus',
  ],
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
  'qualification-run.schema.json': ['QualificationRunView'],
  'discovery-setting-patch-request.schema.json': ['DiscoverySettingPatchRequest'],
  'discovery-setting-view.schema.json': ['DiscoverySettingView'],
  'discovery-topic-patch-request.schema.json': ['DiscoveryTopicPatchRequest'],
  'discovery-topic-view.schema.json': ['DiscoveryTopicView'],
  'discovery-daily-usage-view.schema.json': ['DiscoveryDailyUsageView'],
  'source-auto-score-summary-view.schema.json': ['SourceAutoScoreSummaryView'],
  'source-auto-score-detail-view.schema.json': ['SourceAutoScoreDetailView'],
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
