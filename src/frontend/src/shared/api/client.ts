import { API_BASE_URL } from '../config/app';
import type {
  AgentRun,
  Claim,
  DecisionCreateInput,
  EvidencePage,
  EvidenceIngestInput,
  EvidenceIngestResult,
  Metrics,
  Project,
  ProjectCreateInput,
  Report,
  Concept,
  Innovation,
} from '../types/api';
import { mockApi } from './mockData';

type RequestInitLike = RequestInit & { fallbackMock?: boolean };
const REQUEST_TIMEOUT_MS = 800;
const ENABLE_MOCK_FALLBACK = import.meta.env.VITE_ENABLE_MOCK_FALLBACK === 'true';

function fallback<T>(enabled: boolean, value: () => T, error: unknown): T {
  if (enabled && ENABLE_MOCK_FALLBACK) {
    return value();
  }
  throw error;
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

function normalizeEvidencePage(page: EvidencePage): EvidencePage {
  return {
    ...page,
    items: page.items.map((item) => ({
      ...item,
      excerpt: item.excerpt ?? (item as EvidencePage['items'][number] & { original_excerpt?: string }).original_excerpt ?? '',
      captured_at: item.captured_at ?? (item as EvidencePage['items'][number] & { collected_at?: string }).collected_at ?? '',
    })),
  };
}

async function request<T>(path: string, init?: RequestInitLike): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
      signal: controller.signal,
      ...init,
    });

    if (!response.ok) {
      throw new Error(`HTTP_${response.status}`);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  } catch (error) {
    if (init?.fallbackMock === false) {
      throw error;
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export const api = {
  async listProjects(): Promise<Project[]> {
    try {
      return await request<Project[]>('/projects');
    } catch (error) {
      return fallback(true, () => mockApi.listProjects(), error);
    }
  },

  async createProject(input: ProjectCreateInput): Promise<Project> {
    try {
      return await request<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify(input),
      });
    } catch (error) {
      return fallback(true, () => mockApi.createProject(input), error);
    }
  },

  async getProject(project_id: string): Promise<Project> {
    try {
      return await request<Project>(`/projects/${project_id}`);
    } catch (error) {
      return fallback(true, () => mockApi.getProject(project_id), error);
    }
  },

  async listAgentRuns(project_id: string): Promise<AgentRun[]> {
    try {
      return await request<AgentRun[]>(`/projects/${project_id}/agents`);
    } catch (error) {
      return fallback(true, () => mockApi.listAgentRuns(project_id), error);
    }
  },

  async listEvidence(project_id: string): Promise<EvidencePage> {
    try {
      return normalizeEvidencePage(await request<EvidencePage>(`/projects/${project_id}/evidence`));
    } catch (error) {
      return fallback(true, () => mockApi.listEvidence(project_id), error);
    }
  },

  async ingestEvidence(project_id: string, input: EvidenceIngestInput): Promise<EvidenceIngestResult> {
    return await request<EvidenceIngestResult>(`/projects/${project_id}/evidence`, {
      method: 'POST',
      body: JSON.stringify(input),
    });
  },

  async listClaims(project_id: string): Promise<Claim[]> {
    try {
      return await request<Claim[]>(`/projects/${project_id}/claims`);
    } catch (error) {
      return fallback(true, () => mockApi.listClaims(project_id), error);
    }
  },

  async listConcepts(project_id: string): Promise<Concept[]> {
    try {
      const innovations = await request<Innovation[]>(`/projects/${project_id}/innovations`);
      return innovations.map(toLegacyConcept);
    } catch (error) {
      return fallback(true, () => mockApi.listConcepts(project_id), error);
    }
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
    try {
      return await request<Project>(`/projects/${project_id}/decisions`, {
        method: 'POST',
        body: JSON.stringify(input),
      });
    } catch (error) {
      return fallback(true, () => mockApi.submitDecision(project_id, input), error);
    }
  },

  async deleteProject(project_id: string): Promise<void> {
    try {
      await request(`/projects/${project_id}`, { method: 'DELETE' });
    } catch (error) {
      fallback(true, () => mockApi.deleteProject(project_id), error);
    }
  },

  async startUserResearch(project_id: string): Promise<void> {
    try {
      await request(`/projects/${project_id}/agents/user-research`, { method: 'POST' });
    } catch (error) {
      fallback(true, () => mockApi.startUserResearch(project_id), error);
    }
  },

  async retryInitialResearch(project_id: string): Promise<void> {
    await request(`/projects/${project_id}/research/retry`, { method: 'POST' });
  },

};
