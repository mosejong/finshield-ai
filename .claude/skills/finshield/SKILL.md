---
name: finshield
description: Repository-specific implementation and review rules for FinShield AI.
---
# FinShield Repository Skill

## Language
모든 사용자-facing 답변, 작업 계획, 진행 보고, 코드 리뷰, 결과 요약, 문서 설명은 **반드시 한국어로 작성한다.** 코드 식별자, 라이브러리명, API 경로, 파일명, 표준 기술 용어는 정확성을 위해 원문 영어를 유지해도 된다. 사용자가 명시적으로 다른 언어를 요청한 경우에만 해당 요청 범위에서 예외로 한다.

Read `/CLAUDE.md` and `/SKILL.md` before material changes.
For every feature: classify domain; separate LLM from deterministic financial/safety logic; add tests; preserve official-data provenance; review PII/hostile inputs; run pytest; update ADR when architecture/trust boundaries change.
Never fabricate financial data or add offensive cyber capabilities.
