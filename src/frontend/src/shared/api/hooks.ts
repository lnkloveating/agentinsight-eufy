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

// EventSource has no wildcard listener. Keep this list aligned with the
// backend event names so named SSE events are not silently dropped.
const PROJECT_EVENT_TYPES = [
  'project_created',
  'project_deleted',
  'project_status_changed',
  'agent_status_changed',
  'agent_started',
  'agent_completed',
  'agent_failed',
  'agent_timed_out',
  'agent_cancelled',
  'agent_node_completed',
  'agent_node_skipped',
  'evidence_added',
  'evidence_collection_failed',
  'source_asset_created',
  'source_asset_deleted',
  'source_asset_restored',
  'source_fragment_promoted',
  'media_fragment_reviewed',
  'claim_evaluated',
  'innovation_scored',
  'red_team_reviewed',
  'red_team_routed',
  'workflow_research_handoff_evaluated',
  'workflow_gate_pending',
  'workflow_gate_decided',
  'workflow_revision_started',
  'workflow_finished',
  'source_requirement_scope_updated',
  'source_recovery_resume_prepared',
  'competitor_source_processing_completed',
  'competitor_source_onboarding_completed',
  'a2a_task_started',
  'a2a_task_blocked',
  'search_discovery_started',
  'search_discovery_completed',
  'search_discovery_failed',
] as const;

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
        events: [],
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
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<ProjectEvent[]>(initialEvents);
  const [connectionState, setConnectionState] = useState<'connecting' | 'open' | 'reconnecting' | 'fallback'>(
    'connecting',
  );

  useEffect(() => {
    setEvents((current) => {
      const unchanged =
        current.length === initialEvents.length &&
        current.every((event, index) => event.event_id === initialEvents[index]?.event_id);
      return unchanged ? current : initialEvents;
    });
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

      const appendEvent = (event: MessageEvent<string>) => {
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
          void queryClient.invalidateQueries({ queryKey: ['workspace', projectId] });
          void queryClient.invalidateQueries({ queryKey: ['projects'] });
        } catch {
          setConnectionState('fallback');
        }
      };

      source.onmessage = appendEvent;
      PROJECT_EVENT_TYPES.forEach((eventType) => source.addEventListener(eventType, appendEvent));

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
  }, [projectId, queryClient]);

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
