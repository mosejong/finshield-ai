# 11. Engineering Standards
## Direction
Grow toward api/, schemas/, domain/finance, domain/fraud, services/, clients/, repositories/, models/, core/. Do not create empty abstractions prematurely.
## Errors
Provider/network errors must not become “no eligible products”, zero rates, or invented defaults.
## Observability
Structured logs, request IDs, provider/model latency and errors; no raw sensitive profiles/messages in normal logs.
## Configuration
Environment variables for secrets/DB/providers/features; validate at startup.
## Performance
Measure provider latency, fraud p50/p95, model latency and end-to-end p95 before optimizing.
## Docs
README public overview; docs evidence/design/evaluation/ADRs; CLAUDE.md agent instructions; SKILL.md repeatable engineering procedure.
