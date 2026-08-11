import { API_BASE_URL } from '../config/app';
import type {
  AgentRun,
  Claim,
  Concept,
  DecisionCreateInput,
  EvidenceIngestInput,
  EvidenceIngestResult,
  EvidencePage,
  Innovation,
  Metrics,
  Project,
  ProjectCreateInput,
  Report,
  SourceAssetIngestResult,
  SourceAssetPage,
  SourceLinkCreateInput,
  SourceProcessingStatus,
  ResearchBrief,
} from '../types/api';

type RequestInitLike = RequestInit & { timeoutMs?: number };
const DEFAULT_REQUEST_TIMEOUT_MS = parsePositiveIntegerEnv(import.meta.env.VITE_API_REQUEST_TIMEOUT_MS, 30_000);
const LONG_REQUEST_TIMEOUT_MS = parsePositiveIntegerEnv(import.meta.env.VITE_API_LONG_REQUEST_TIMEOUT_MS, 800_000);

function parsePositiveIntegerEnv(value: string | undefined, fallbackValue: number): number {
  if (!value) {
    return fallbackValue;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallbackValue;
}

function toLegacyConcept(innovation: Innovation): Concept {
  return {
    concept_id: innovation.innovation_id,
    name: innovation.name,
    target_user: innovation.target_user.description,
    value_proposition: innovation.event_understanding.recommended_action,
    supporting_evidence_ids: innovation.evidence_ids,
    risks: innovation.red_team_review?.technical_risks ?? [],
    red_team_findings: innovation.red_team_review?.required_actions ?? [],
    scores: Object.fromEntries(
      Object.entries(innovation.score_breakdown).map(([key, component]) => [key, component.score]),
    ),
    status: innovation.status,
  };
}

function normalizeBrief(brief: ResearchBrief): Project['brief'] {
  if (
    !brief.target_ecosystems ||
    !brief.target_users ||
    !brief.markets ||
    !brief.risk_scenarios ||
    !brief.privacy_boundary ||
    !brief.intervention_boundary ||
    !brief.evaluation_dimensions
  ) {
    return brief;
  }

  return {
    ...brief,
    category: brief.target_ecosystems.join(' / '),
    target_user: brief.target_users.join(' / '),
    region: brief.markets.join(' / '),
    scenarios: brief.risk_scenarios,
    constraints: [
      brief.privacy_boundary.raw_media_allowed ? '允许原始媒体' : '不使用原始媒体',
      brief.privacy_boundary.external_sharing_allowed ? '允许外部共享' : '禁止外部共享',
      ...brief.privacy_boundary.restricted_zones.map((zone) => `限制区域：${zone}`),
      ...brief.intervention_boundary.prohibited_actions.map((action) => `禁止：${action}`),
    ],
    focus_dimensions: brief.evaluation_dimensions,
  };
}

function normalizeProject(project: Project): Project {
  return {
    ...project,
    brief: normalizeBrief(project.brief),
  };
}

function normalizeEvidencePage(page: EvidencePage): EvidencePage {
  return {
    ...page,
    items: page.items.map((item) => ({
      ...item,
      excerpt: item.excerpt ?? item.original_excerpt ?? '',
      captured_at: item.captured_at ?? item.collected_at ?? '',
    })),
  };
}

async function request<T>(path: string, init?: RequestInitLike): Promise<T> {
  const controller = new AbortController();
  const { timeoutMs, ...fetchInit } = init ?? {};
  const isFormData = typeof FormData !== 'undefined' && fetchInit.body instanceof FormData;
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS,
  );

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(fetchInit.headers ?? {}),
      },
      ...fetchInit,
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      throw new Error(detail ? `HTTP_${response.status}: ${detail}` : `HTTP_${response.status}`);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export const api = {
  async listProjects(): Promise<Project[]> {
    return (await request<Project[]>('/projects')).map(normalizeProject);
  },

  async createProject(input: ProjectCreateInput): Promise<Project> {
    return normalizeProject(await request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(input),
    }));
  },

  async getProject(project_id: string): Promise<Project> {
    return normalizeProject(await request<Project>(`/projects/${project_id}`));
  },

  async listAgentRuns(project_id: string): Promise<AgentRun[]> {
    return await request<AgentRun[]>(`/projects/${project_id}/agents`);
  },

  async listEvidence(project_id: string): Promise<EvidencePage> {
    return normalizeEvidencePage(await request<EvidencePage>(`/projects/${project_id}/evidence`));
  },

  async ingestEvidence(project_id: string, input: EvidenceIngestInput): Promise<EvidenceIngestResult> {
    return await request<EvidenceIngestResult>(`/projects/${project_id}/evidence`, {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  async listClaims(project_id: string): Promise<Claim[]> {
    return await request<Claim[]>(`/projects/${project_id}/claims`);
  },

  async listConcepts(project_id: string): Promise<Concept[]> {
    const innovations = await request<Innovation[]>(`/projects/${project_id}/innovations`);
    return innovations.map(toLegacyConcept);
  },

  async getReport(project_id: string): Promise<Report | null> {
    try {
      return await request<Report>(`/projects/${project_id}/report`);
    } catch {
      return null;
    }
  },

  async getMetrics(project_id: string): Promise<Metrics | null> {
    try {
      return await request<Metrics>(`/projects/${project_id}/metrics`);
    } catch {
      return null;
    }
  },

  async submitDecision(project_id: string, input: DecisionCreateInput): Promise<Project> {
    return normalizeProject(await request<Project>(`/projects/${project_id}/decisions`, {
      method: 'POST',
      body: JSON.stringify(input),
    }));
  },

  async deleteProject(project_id: string): Promise<void> {
    await request(`/projects/${project_id}`, { method: 'DELETE' });
  },

  async startUserResearch(project_id: string): Promise<void> {
    await request(`/projects/${project_id}/agents/user-research`, {
      method: 'POST',
      timeoutMs: LONG_REQUEST_TIMEOUT_MS,
    });
  },

  async runCompetitorEcosystem(project_id: string): Promise<unknown> {
    return await request(`/projects/${project_id}/agents/competitor-ecosystem`, {
      method: 'POST',
      timeoutMs: LONG_REQUEST_TIMEOUT_MS,
    });
  },

  async retryInitialResearch(project_id: string): Promise<void> {
    await request(`/projects/${project_id}/research/retry`, {
      method: 'POST',
      timeoutMs: LONG_REQUEST_TIMEOUT_MS,
    });
  },

  async listSources(project_id: string): Promise<SourceAssetPage> {
    return await request<SourceAssetPage>(`/projects/${project_id}/sources`);
  },

  async createSourceLink(project_id: string, input: SourceLinkCreateInput): Promise<SourceAssetIngestResult> {
    return await request<SourceAssetIngestResult>(`/projects/${project_id}/sources/links`, {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  async uploadSourceFile(
    project_id: string,
    input: {
      file: File;
      authorization_basis: string;
      authorization_confirmed: boolean;
      authorized_by: string;
      purpose: string;
    },
  ): Promise<SourceAssetIngestResult> {
    const body = new FormData();
    body.append('file', input.file);
    body.append('authorization_basis', input.authorization_basis);
    body.append('authorization_confirmed', String(input.authorization_confirmed));
    body.append('authorized_by', input.authorized_by);
    body.append('purpose', input.purpose);
    return await request<SourceAssetIngestResult>(`/projects/${project_id}/sources/files`, {
      method: 'POST',
      body,
      timeoutMs: LONG_REQUEST_TIMEOUT_MS,
    });
  },

  async processSource(project_id: string, source_asset_id: string): Promise<SourceProcessingStatus> {
    return await request<SourceProcessingStatus>(`/projects/${project_id}/sources/${source_asset_id}/processing`, {
      method: 'POST',
      timeoutMs: LONG_REQUEST_TIMEOUT_MS,
    });
  },
};
