export type ProjectStatus =
  | 'draft'
  | 'awaiting_brief_approval'
  | 'researching'
  | 'awaiting_concept_approval'
  | 'supplementing_research'
  | 'generating_report'
  | 'awaiting_final_approval'
  | 'completed'
  | 'failed'
  | 'terminated';

export type AgentRunStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'waiting'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'blocked'
  | 'needs_revision'
  | 'cancelled';

export type DecisionAction = 'approve' | 'revise' | 'research_more' | 'reject' | 'terminate';

export type ViewMode = 'brief' | 'live' | 'evidence' | 'concepts' | 'proposal';

export type ResearchScope = 'home_safety_ecosystem';
export type HomeSafetyDomain =
  | 'general_home_safety'
  | 'property_security'
  | 'personal_safety'
  | 'elder_safety'
  | 'child_safety'
  | 'perimeter_safety';
export type AuthorizedSignalType =
  | 'visual_event_metadata'
  | 'motion_event'
  | 'door_event'
  | 'device_status'
  | 'household_presence'
  | 'user_confirmation'
  | 'environment_context'
  | 'simulated_event';
export type AllowedIntervention =
  | 'continue_observing'
  | 'request_additional_signal'
  | 'local_prompt'
  | 'ask_user'
  | 'notify_authorized_contact'
  | 'preserve_evidence';
export type ResearchDeliverable =
  | 'ecosystem_opportunity_portfolio'
  | 'device_capability_gap'
  | 'policy_dry_run'
  | 'pilot_recommendation';

export interface ResearchSourcePermissions {
  public_sources: boolean;
  user_uploaded_materials: boolean;
  enterprise_internal_materials: boolean;
  authorized_household_events: boolean;
}

export interface ResearchPrivacyBoundary {
  raw_media_allowed: boolean;
  restricted_zones: string[];
  retention_policy: string;
  external_sharing_allowed: boolean;
}

export interface ResearchInterventionBoundary {
  allowed_interventions: AllowedIntervention[];
  prohibited_actions: string[];
  high_impact_action_requires_human_approval: true;
}

export interface BackendResearchBrief {
  question: string;
  research_scope: ResearchScope;
  safety_domains: HomeSafetyDomain[];
  target_ecosystems: string[];
  comparison_ecosystems: string[];
  target_users: string[];
  markets: string[];
  time_horizon: string;
  safety_goals: string[];
  risk_scenarios: string[];
  authorized_signal_types: AuthorizedSignalType[];
  privacy_boundary: ResearchPrivacyBoundary;
  intervention_boundary: ResearchInterventionBoundary;
  forbidden_inferences: string[];
  evaluation_dimensions: string[];
  validation_expectations: string[];
  source_permissions: ResearchSourcePermissions;
  deliverables: ResearchDeliverable[];
}

export interface ResearchBrief extends Partial<BackendResearchBrief> {
  // Derived display aliases for older UI components.
  question: string;
  category: string;
  target_user: string;
  region: string;
  scenarios: string[];
  constraints: string[];
  focus_dimensions: string[];
}

export interface PendingDecision {
  decision_id: string;
  gate: string;
  allowed_actions: DecisionAction[];
}

export interface Project {
  project_id: string;
  status: ProjectStatus;
  current_stage: string;
  progress: number;
  brief: ResearchBrief;
  model_selection?: ModelSelection | null;
  pending_decision: PendingDecision | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreateInput {
  brief: BackendResearchBrief;
  model_selection?: ModelSelection | null;
}

export interface ModelSelection {
  default_model_id: string;
  agent_overrides?: Record<string, string>;
}

export interface DecisionCreateInput {
  decision_id: string;
  action: DecisionAction;
  reason: string;
  actor: string;
  selected_concept_ids: string[];
}

export interface AgentRun {
  agent_run_id: string;
  project_id: string;
  agent_type: string;
  agent_name: string;
  status: AgentRunStatus;
  progress: number;
  message: string;
  started_at: string | null;
  completed_at: string | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface ProjectEvent {
  event_id: string;
  event_type: string;
  project_id: string;
  sequence_number: number;
  timestamp: string;
  data: Record<string, unknown>;
  trace_id: string;
}

export interface Evidence {
  evidence_id: string;
  source_url: string | null;
  source_domain?: string | null;
  source_asset_id?: string | null;
  source_fragment_id?: string | null;
  source_type: string;
  title: string;
  original_excerpt?: string;
  excerpt: string;
  captured_at: string;
  collected_at?: string;
  status: string;
  content_hash: string;
  confidence: number;
}

export interface EvidencePage {
  items: Evidence[];
  next_cursor: string | null;
  total: number;
}

export interface EvidenceIngestInput {
  source_url: string;
  source_type: string;
  title: string;
  original_excerpt: string;
  claim_type: 'user_opinion' | 'fact';
  product?: string;
  region?: string;
  user_segment?: string;
  collected_at: string;
  status: 'verified' | 'partially_verified' | 'unverified';
  confidence: number;
  authority_score: number;
  recency_score: number;
  diversity_score: number;
}

export interface EvidenceIngestResult {
  evidence: Evidence;
  created: boolean;
}

export type SourceAuthorizationBasis = 'user_owned' | 'enterprise_authorized' | 'publicly_available';
export type SourceAssetKind = 'file' | 'link' | 'user_input';
export type SourceAssetStatus = 'ready' | 'deleted';
export type SourceMediaCategory = 'document' | 'dataset' | 'image' | 'video' | 'audio' | 'webpage';
export type CollectionJobStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'blocked' | 'failed' | 'cancelled';

export interface SourceLinkCreateInput {
  source_url: string;
  display_name: string;
  authorization_basis: SourceAuthorizationBasis;
  authorization_confirmed: true;
  authorized_by: string;
  purpose: string;
}

export interface SourceAsset {
  source_asset_id: string;
  project_id: string;
  kind: SourceAssetKind;
  status: SourceAssetStatus;
  display_name: string;
  original_filename: string | null;
  source_url: string | null;
  media_type: string;
  media_category: SourceMediaCategory;
  content_hash: string;
  byte_size: number;
  authorization_basis: SourceAuthorizationBasis;
  authorization_confirmed_at: string;
  authorized_by: string;
  purpose: string;
  collection_job_id: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface SourceAssetIngestResult {
  source_asset: SourceAsset;
  created: boolean;
}

export interface SourceAssetPage {
  items: SourceAsset[];
  next_cursor: string | null;
  total: number;
}

export interface SourceProcessingJob {
  collection_job_id: string;
  project_id: string;
  source_asset_id: string;
  source_type: string;
  status: CollectionJobStatus;
  attempt_count: number;
  progress: number;
  result: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface SourceProcessingStatus {
  job: SourceProcessingJob;
  parsed_artifact: {
    parsed_artifact_id: string;
    project_id: string;
    source_asset_id: string;
    collection_job_id: string;
    parser_id: string;
    parser_version: string;
    fragment_count: number;
    created_at: string;
  } | null;
}

export interface Claim {
  claim_id: string;
  statement: string;
  evidence_ids: string[];
  contradicting_evidence_ids: string[];
  status: string;
}

export interface Concept {
  concept_id: string;
  name: string;
  target_user: string;
  value_proposition: string;
  supporting_evidence_ids: string[];
  risks: string[];
  red_team_findings: string[];
  scores: Record<string, number>;
  status: string;
}

export interface Innovation {
  innovation_id: string;
  name: string;
  status: string;
  target_user: { description: string };
  event_understanding: { recommended_action: string };
  evidence_ids: string[];
  score_breakdown: Record<string, { score: number }>;
  red_team_review?: {
    technical_risks?: string[];
    required_actions?: string[];
  } | null;
}

export interface Report {
  report_id: string;
  project_id: string;
  version: number;
  recommendation: string;
  sections: Record<string, unknown>;
  cited_evidence_ids: string[];
  unknowns: string[];
  generated_at: string;
}

export interface Metrics {
  elapsed_seconds: number;
  valid_evidence_count: number;
  citation_coverage: number;
  source_diversity: number;
  estimated_cost: number;
  comparison: Record<string, unknown>;
}

export interface WorkspaceData {
  project: Project;
  agentRuns: AgentRun[];
  evidencePage: EvidencePage;
  claims: Claim[];
  concepts: Concept[];
  report: Report | null;
  metrics: Metrics | null;
  events: ProjectEvent[];
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
  trace_id?: string;
}
