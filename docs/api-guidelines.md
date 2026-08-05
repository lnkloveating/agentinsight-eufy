# API Guidelines

- The implemented lifecycle scaffold remains under `/api/v1`; the AIPDF event-understanding target contract is versioned under `/api/v2`.
- `docs/api/openapi.yaml` describes the `/api/v2` target contract. Runtime code must not advertise v2 until the implementation and contract tests are complete.
- JSON fields use `snake_case`.
- Timestamps use RFC 3339 UTC.
- IDs use opaque strings with prefixes such as `proj_`, `ev_`, `claim_`, `inv_`, `decision_`, and `demo_`.
- Errors use one envelope: `code`, `message`, `details`, `trace_id`.
- List endpoints expose `items`, `next_cursor`, and `total` when known.
- Retriable mutations require an `Idempotency-Key` header and persist the request outcome.
- SSE uses the default `message` event so browser `onmessage` handlers receive it; each data object contains `event_id`, `event_type`, `project_id`, `sequence_number`, `timestamp`, `data`, and `trace_id`.
- Aily-facing endpoints use a service Bearer token and never accept Feishu `app_secret` or access tokens from request bodies.
- Feishu callbacks use their platform event identifier as an idempotency key after verification.
- Breaking changes require a new API version.
