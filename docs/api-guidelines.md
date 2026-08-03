# API Guidelines

- Base path: `/api/v1`.
- JSON fields use `snake_case`.
- Timestamps use RFC 3339 UTC.
- IDs use opaque strings with prefixes such as `proj_`, `ev_`, `claim_`, `concept_`.
- Errors use one envelope: `code`, `message`, `details`, `trace_id`.
- List endpoints expose `items`, `next_cursor`, and `total` when known.
- Mutations accept an `Idempotency-Key` header where retries may duplicate work.
- SSE events contain `event_id`, `event_type`, `project_id`, `timestamp`, and `data`.
- Breaking changes require a new API version.
