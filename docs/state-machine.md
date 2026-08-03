# Project State Machine

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> awaiting_brief_approval
    awaiting_brief_approval --> researching: approve
    awaiting_brief_approval --> terminated: terminate
    researching --> awaiting_concept_approval
    researching --> failed
    failed --> researching: retry
    awaiting_concept_approval --> supplementing_research: research_more
    supplementing_research --> awaiting_concept_approval
    awaiting_concept_approval --> generating_report: approve
    awaiting_concept_approval --> terminated: reject_all
    generating_report --> awaiting_final_approval
    generating_report --> failed
    awaiting_final_approval --> generating_report: revise
    awaiting_final_approval --> completed: approve
    awaiting_final_approval --> terminated: terminate
```
