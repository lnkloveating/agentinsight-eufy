import { API_BASE_URL } from '../config/app';
import type {
  AgentRun,
  Claim,
  DecisionCreateInput,
  EvidencePage,
  Metrics,
  Project,
  ProjectCreateInput,
  ProjectEvent,
  Report,
  Concept,
} from '../types/api';
import { mockApi } from './mockData';

type RequestInitLike = RequestInit & { fallbackMock?: boolean };
const REQUEST_TIMEOUT_MS = 800;

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
    } catch {
      return mockApi.listProjects();
    }
  },

  async createProject(input: ProjectCreateInput): Promise<Project> {
    try {
      return await request<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify(input),
      });
    } catch {
      return mockApi.createProject(input);
    }
  },

  async getProject(project_id: string): Promise<Project> {
    try {
      return await request<Project>(`/projects/${project_id}`);
    } catch {
      return mockApi.getProject(project_id);
    }
  },

  async listAgentRuns(project_id: string): Promise<AgentRun[]> {
    try {
      return await request<AgentRun[]>(`/projects/${project_id}/agents`);
    } catch {
      return mockApi.listAgentRuns(project_id);
    }
  },

  async listEvidence(project_id: string): Promise<EvidencePage> {
    try {
      return await request<EvidencePage>(`/projects/${project_id}/evidence`);
    } catch {
      return mockApi.listEvidence(project_id);
    }
  },

  async listClaims(project_id: string): Promise<Claim[]> {
    try {
      return await request<Claim[]>(`/projects/${project_id}/claims`);
    } catch {
      return mockApi.listClaims(project_id);
    }
  },

  async listConcepts(project_id: string): Promise<Concept[]> {
    try {
      return await request<Concept[]>(`/projects/${project_id}/concepts`);
    } catch {
      return mockApi.listConcepts(project_id);
    }
  },

  async getReport(project_id: string): Promise<Report | null> {
    try {
      return await request<Report>(`/projects/${project_id}/report`);
    } catch {
      return mockApi.getReport(project_id);
    }
  },

  async getMetrics(project_id: string): Promise<Metrics | null> {
    try {
      return await request<Metrics>(`/projects/${project_id}/metrics`);
    } catch {
      return mockApi.getMetrics(project_id);
    }
  },

  async submitDecision(project_id: string, input: DecisionCreateInput): Promise<Project> {
    try {
      return await request<Project>(`/projects/${project_id}/decisions`, {
        method: 'POST',
        body: JSON.stringify(input),
      });
    } catch {
      return mockApi.submitDecision(project_id, input);
    }
  },

  async deleteProject(project_id: string): Promise<void> {
    await request(`/projects/${project_id}`, { method: 'DELETE' });
  },

  listMockEvents(project_id: string): ProjectEvent[] {
    return mockApi.listEvents(project_id);
  },
};
