# Frontend

React/TypeScript shell for the five core experiences. The current client consumes `/api/v1` and falls back to local Mock data for unfinished endpoints. It must not switch to the `/api/v2` target contract until generated/shared types and backend contract tests are ready.

The five target experiences are Brief, live research, Evidence center, candidate-scenario arena, and final proposal/method comparison. Mock records are presentation fixtures only and must never be represented as real market evidence.

```powershell
npm install
npm run frontend:dev
```
