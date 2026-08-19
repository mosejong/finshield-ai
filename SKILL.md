# FinShield AI Development Skill

## Language
모든 사용자-facing 답변, 작업 계획, 진행 보고, 리뷰, 결과 요약, 문서 설명은 **반드시 한국어로 작성한다.** 코드 식별자, 라이브러리명, API 경로, 파일명, 표준 기술 용어는 필요하면 원문 영어를 유지할 수 있다. 사용자가 명시적으로 다른 언어를 요청한 경우에만 해당 범위에서 예외로 한다.

## Done means
Implemented + tested + error/fallback handling + privacy/security review + provenance + docs + full tests passing.

## Financial profile
Read docs/09-financial-profile-schema.md. Minimum necessary data; prefer ranges when exact values are unnecessary; derived metrics reproducible.

## Product/loan data
Read docs/07-official-api-candidates.md. Official source of truth. Normalize but retain provider, source product ID, fetched_at, source reference. Never infer missing rate/eligibility.

## Loan simulation
No LLM math. Deterministic functions with tests for normal/boundary rates, terms, rounding, invalid inputs and repayment methods. Return assumptions.

## Fraud/security
Read docs/01-problem-definition.md, 08-ai-security-alignment.md, 12-security-threat-model.md. Structured signals include urgency, credential request, account/card access, remote-app install, receive-and-forward money, impersonation, unofficial links. Keyword rules are bootstrap only.

## Scenario engine
States: received_only, clicked_link, shared_personal_info, shared_account_access, installed_app, received_unknown_money, transferred_money. Map guidance to verified official procedures.

## LLM
Allowed: grounded explanation, safe clarification, evidence summary, plain-language translation.
Forbidden: invented eligibility, repayment calculation, overriding safety blocks, unsupported legal conclusions, arbitrary URL browsing.

## API direction
/api/v1/auth/session
/api/v1/auth/account
/api/v1/profiles
/api/v1/profiles/{profile_id}/metrics
/api/v1/products
/api/v1/loans/simulate
/api/v1/analyze
/api/v1/analyze/explanation
/api/v1/recommendations
/api/v1/guidance/wealth

Fraud evidence is returned as `official_sources` in the analyze response.

## Review
Correctness: deterministic math, assumptions, mappings, missing values.
Safety: hostile input, injection, sensitive logging, stale data.
Product: actionable, personalized, explained, sourced.
Portfolio: baseline, comparison, defensible architecture, reproducibility.
