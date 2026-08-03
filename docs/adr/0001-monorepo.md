# ADR 0001: Monorepo with API-first boundaries

## Status

Accepted.

## Decision

Keep frontend, backend, shared contracts, infrastructure and acceptance tests in one repository. The OpenAPI document is the public integration contract.

## Consequences

Frontend and backend can develop independently against stable schemas, while CI can detect contract drift in one place.
