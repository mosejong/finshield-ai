---
name: finshield
description: Repository-specific implementation and review rules for FinShield AI.
---
# FinShield Repository Skill
사용자-facing 답변·계획·보고·리뷰·요약·문서 설명은 반드시 한국어로 작성한다. 코드 식별자·라이브러리명·API 경로·파일명·표준 기술 용어는 원문 영어를 유지해도 된다.
Read `/AGENTS.md` and `/SKILL.md` before material changes.
For every feature: classify domain; separate LLM from deterministic financial/safety logic; add tests; preserve official-data provenance; review PII/hostile inputs; run pytest; update ADR when architecture/trust boundaries change.
Never fabricate financial data or add offensive cyber capabilities.
