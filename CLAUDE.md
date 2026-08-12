# CLAUDE.md — FinShield AI Agent Guide
## Mission
Build FinShield AI: personalized financial decision support + official financial data + fraud/social-engineering defense + AI-service security. Target: 2026 Finance AI Challenge and a production-quality fintech backend portfolio.

## Non-negotiables
- LLMs are not the sole authority for eligibility, financial math, risk scores, or safety actions.
- Official APIs are source of truth for products/rates/policy facts; retain provenance and freshness.
- Deterministic code handles financial math; rules/evaluated ML handle structured risk; LLMs explain grounded results.
- Never fabricate products, rates, eligibility, laws, institutions, or official guidance.
- Minimize PII; never request RRN, bank passwords, OTPs, full card credentials, or unnecessary account numbers.
- Treat user URLs as hostile; no arbitrary server-side URL fetching.
- No offensive phishing, credential theft, malware, evasion, or financial-abuse features.

## Read before coding
README.md -> SKILL.md -> relevant docs -> existing code/tests.

## Stack
Python 3.12, FastAPI, Pydantic v2, PostgreSQL, SQLAlchemy 2.x, Alembic, pytest, Docker, GitHub Actions. Redis only for demonstrated need.

## Architecture
Client -> validation/privacy -> profile/input -> deterministic/ML engines -> official evidence/data -> LLM explanation -> output validation. Never collapse this into one prompt.

## Engineering
Thin routes; domain/service business logic; external-provider adapters; pure/testable financial calculations; explicit schemas; type hints; no secrets; explicit provider failures; tests for meaningful changes.

## Evaluation
Track relevant precision/recall/F1, class recall, FPR, scenario accuracy, unsupported claims, evidence coverage, p50/p95 and fallback/error rates. Compare Rule-only vs LLM-only vs Hybrid.

## Security
Threat model: prompt/indirect injection, retrieval poisoning, SSRF, hostile URLs, PII/secret leakage, hallucinated guidance, stale data, log leakage, excessive retention, API/tool abuse. New external fetch/upload/tool/sensitive field requires review.

## Agent protocol
Before: inspect docs/code/tests; choose smallest coherent change.
After: `pytest -q`; review diff; check privacy/security; update docs; report uncertainty.
Use small commits: feat/fix/test/docs/refactor/chore.
P0 first: see docs/10-mvp-backlog.md.
