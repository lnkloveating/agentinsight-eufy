# MVP Acceptance Criteria

Each criterion must have an automated test, a traceable demonstration step, or both.

## AC-01 Research brief

Given an ambiguous research request, the system exposes a structured brief containing category, target user, region, scenario, constraints and focus dimensions, then waits for confirmation.

## AC-02 Project lifecycle

A project follows the documented state machine. Invalid transitions are rejected and every accepted transition records timestamp, actor and reason.

## AC-03 Workflow recovery

The workflow supports conditional branches, bounded loops, checkpoints and recovery without restarting unaffected completed stages.

## AC-04 Human decisions

Brief approval, concept promotion and final definition can pause the workflow. Approve, revise, research-more, reject and terminate decisions are auditable.

## AC-05 Evidence collection

Evidence requests support source planning, cache lookup, deduplication, budget limits, collection status and structured results.

## AC-06 Evidence Lake

Every evidence record stores source URL, source type, captured text or artifact reference, capture time, status, content hash, scope, confidence and stable Evidence ID.

## AC-07 Claim gate

A factual claim without at least one valid supporting Evidence ID cannot be promoted into the final report. Conflicts and unknowns remain visible.

## AC-08 Competitor A2A

The competitor supervisor can discover three specialist Agent Cards, issue structured tasks and collect official-product, price-channel and user-review artifacts.

## AC-09 Deep Research web

The five core experiences are operable: create task, live research, evidence center, concept arena, and final proposal/method comparison. Loading, empty, failed and resumed states are represented.

## AC-10 Observability

Project, workflow run, agent run, A2A task, MCP call, crawl job, evidence and claim share traceable identifiers. A local trace remains available when the external observability service fails.

## AC-11 Final proposal

The proposal includes target users, jobs, evidence coverage, problem severity, concept, feature-to-evidence mapping, competitor differentiation, feasibility, business assumptions, MVP, success metrics, limitations, unknowns and stop conditions.

## AC-12 Method comparison

AI-assisted and traditional product-definition runs can be compared on elapsed time, valid evidence, citation coverage, source diversity, false-demand detection, duplicate-product detection, technical-risk detection, traceability, blind-review score and cost.

## Release gate

The MVP is accepted only when one eufy scenario runs end to end, survives one forced failure, pauses and resumes at a human gate, and produces a report whose key facts can be traced to source evidence.
