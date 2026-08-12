---
name: finshield
description: Repository-specific implementation and review rules for FinShield AI.
---
# FinShield Repository Skill
Read `/CLAUDE.md` and `/SKILL.md` before material changes.
For every feature: classify domain; separate LLM from deterministic financial/safety logic; add tests; preserve official-data provenance; review PII/hostile inputs; run pytest; update ADR when architecture/trust boundaries change.
Never fabricate financial data or add offensive cyber capabilities.
