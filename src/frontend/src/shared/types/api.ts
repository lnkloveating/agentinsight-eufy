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

export type AgentRunStatus = 'queued' | 'running' | 'waiting' | 'completed' | 'failed' | 'cancelled';

export type DecisionAction = 'approve' | 'revise' | 'research_more' | 'reject' | 'terminate';

export type ViewMode = 'brief' | 'live' | 'evidence' | 'concepts' | 'proposal';

export interface ResearchBrief {
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
  pending_decision: PendingDecision | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreateInput {
  brief: ResearchBrief;
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
  source_url: string;
  source_type: string;
  title: string;
  excerpt: string;
  captured_at: string;
  status: string;
  content_hash: string;
  confidence: number;
}

export interface EvidencePage {
  items: Evidence[];
  next_cursor: string | null;
  total: number;
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
