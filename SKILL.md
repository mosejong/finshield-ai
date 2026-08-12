# FinShield AI Development Skill
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
/api/v1/profiles
/api/v1/products
/api/v1/loans/simulate
/api/v1/fraud/analyze
/api/v1/recommendations
/api/v1/evidence

## Review
Correctness: deterministic math, assumptions, mappings, missing values.
Safety: hostile input, injection, sensitive logging, stale data.
Product: actionable, personalized, explained, sourced.
Portfolio: baseline, comparison, defensible architecture, reproducibility.
