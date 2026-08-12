# ADR-0001: Hybrid Decision Architecture
Status: Accepted for MVP
Date: 2026-08-11
## Context
LLM-only creates unacceptable uncertainty for financial calculations, eligibility, official facts and safety actions.
## Decision
Deterministic financial calculations + official product APIs + rules/evaluated ML for risk signals + scenario engine + grounded LLM explanation.
## Consequences
Better testability/provenance/safety and measurable baselines; more components and upfront design work.
