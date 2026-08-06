# Documentation map

## Current implementation status

- `backend-progress-summary.md` records the backend baseline currently merged to `main`, the real `/api/v1` availability boundary, and the frontend adaptation checklist. Read it before integrating frontend pages with backend data.

## Product and research

1. `research-flow.md` is the canonical bridge from industry opportunity research to candidate comparison, Feishu approval and the selected scenario Demo.
2. `agent-contracts.md` defines six Agent roles, structured artifacts, dependencies, quality scoring and mandatory rework.
3. `state-machine.md` defines project states, terminal meanings and the three Human in the Loop gates.

## Engineering contracts

1. `architecture.md` defines runtime boundaries and Feishu's collaboration role.
2. `api-guidelines.md` defines versioning, identifiers, idempotency, SSE and Feishu API rules.
3. `api/openapi.yaml` is the `/api/v2` target HTTP contract. The current runtime remains `/api/v1` until v2 implementation is complete.
4. `acceptance-criteria.md` is the release authority for the MVP.
5. `../tests/acceptance/features/end_to_end.feature` expresses the same release behavior as executable Chinese Gherkin scenarios.

## Supporting documents

- `../eufy调研报告.md` contains the competition proposal, research background and full target architecture.
- `设计方案.md` and the visual/component guidelines govern the current frontend presentation.
- `adr/0001-monorepo.md` records the API-first repository boundary.

## Precedence

For scope and behavior conflicts, use this order:

1. `acceptance-criteria.md` and `api/openapi.yaml` for release and public behavior;
2. `state-machine.md` and `agent-contracts.md` for workflow and structured artifacts;
3. `research-flow.md` for product logic and Feishu placement;
4. the full research report and UI design documents for background and presentation.

Mock fixtures, demo seed data and the current v1 implementation describe existing behavior, not market facts and not the completed v2 product.
