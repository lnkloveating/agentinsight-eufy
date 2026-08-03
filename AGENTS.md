# Repository Instructions

- Preserve the API-first split between `src/frontend` and `src/backend`.
- Update `docs/api/openapi.yaml` before changing a public API.
- Never allow an unsupported factual claim into a final report without an Evidence ID.
- Keep deterministic parsing, validation and persistence separate from LLM reasoning.
- Do not commit secrets, captured personal data, generated evidence, or runtime traces.
- Add tests at the lowest useful level and map end-to-end behavior to `docs/acceptance-criteria.md`.
