import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { DEFAULT_ACTOR } from '../config/app';
import { API_BASE_URL } from '../config/app';
import type {
  DecisionAction,
  Metrics,
  Project,
  ProjectCreateInput,
  ProjectEvent,
  ViewMode,
  WorkspaceData,
} from '../types/api';
import { api } from './client';

export function useProjectsQuery() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  });
}

export function useCreateProjectMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ProjectCreateInput) => api.createProject(input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });
}

export function useWorkspaceQuery(projectId: string) {
  return useQuery<WorkspaceData>({
    queryKey: ['workspace', projectId],
    queryFn: async () => {
      const [project, agentRuns, evidencePage, claims, concepts, report, metrics] = await Promise.all([
        api.getProject(projectId),
        api.listAgentRuns(projectId),
        api.listEvidence(projectId),
        api.listClaims(projectId),
        api.listConcepts(projectId),
        api.getReport(projectId),
        api.getMetrics(projectId),
      ]);

      return {
        project,
        agentRuns,
        evidencePage,
        claims,
        concepts,
        report,
        metrics,
        events: api.listMockEvents(projectId),
      };
    },
    enabled: !!projectId,
  });
}

export function useDecisionMutation(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: { decisionId: string; action: DecisionAction; reason: string; selectedConceptIds?: string[] }) =>
      api.submitDecision(projectId, {
        decision_id: input.decisionId,
        action: input.action,
        actor: DEFAULT_ACTOR,
        reason: input.reason,
        selected_concept_ids: input.selectedConceptIds ?? [],
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
        queryClient.invalidateQueries({ queryKey: ['workspace', projectId] }),
      ]);
    },
  });
}

export function useProjectEvents(projectId: string, initialEvents: ProjectEvent[]) {
  const [events, setEvents] = useState<ProjectEvent[]>(initialEvents);
  const [connectionState, setConnectionState] = useState<'connecting' | 'open' | 'reconnecting' | 'fallback'>(
    'connecting',
  );

  useEffect(() => {
    setEvents(initialEvents);
  }, [initialEvents]);

  useEffect(() => {
    let cancelled = false;
    let reconnectTimer: number | undefined;

    try {
      const source = new EventSource(`${API_BASE_URL}/projects/${projectId}/events`);

      source.onopen = () => {
        if (!cancelled) {
          setConnectionState('open');
        }
      };

      source.onmessage = (event) => {
        if (cancelled) {
          return;
        }

        try {
          const nextEvent = JSON.parse(event.data) as ProjectEvent;
          setEvents((current) => {
            if (current.some((item) => item.event_id === nextEvent.event_id)) {
              return current;
            }
            return [...current, nextEvent].sort((a, b) => a.sequence_number - b.sequence_number);
          });
        } catch {
          setConnectionState('fallback');
        }
      };

      source.onerror = () => {
        if (cancelled) {
          return;
        }
        setConnectionState('reconnecting');
        reconnectTimer = window.setTimeout(() => {
          setConnectionState('fallback');
        }, 1_500);
      };

      return () => {
        cancelled = true;
        source.close();
        if (reconnectTimer) {
          window.clearTimeout(reconnectTimer);
        }
      };
    } catch {
      setConnectionState('fallback');
      return undefined;
    }
  }, [projectId]);

  return { events, connectionState };
}

export function useResolvedView(project: Project | undefined, currentView: ViewMode | null): ViewMode {
  if (currentView) {
    return currentView;
  }

  if (!project) {
    return 'brief';
  }

  switch (project.status) {
    case 'awaiting_brief_approval':
    case 'draft':
      return 'brief';
    case 'awaiting_concept_approval':
      return 'concepts';
    case 'awaiting_final_approval':
    case 'completed':
      return 'proposal';
    default:
      return 'live';
  }
}

export function summarizeMetrics(metrics: Metrics | null | undefined) {
  if (!metrics) {
    return [];
  }

  return [
    { label: '有效证据', value: String(metrics.valid_evidence_count) },
    { label: '引用覆盖', value: `${Math.round(metrics.citation_coverage * 100)}%` },
    { label: '来源多样性', value: String(metrics.source_diversity) },
    { label: '预计成本', value: `$${metrics.estimated_cost.toFixed(1)}` },
  ];
}
