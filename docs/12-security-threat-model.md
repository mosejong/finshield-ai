# 12. Security Threat Model
## Assets
Financial profiles, fraud inputs, official product data, API credentials, prompts, results, evaluation/audit data.
## Trust boundaries
Client->API; API->official providers; API->model provider; API->DB/cache; evidence ingestion->retrieval.
## Threats & controls
User text: injection/oversize/PII -> limits, instruction-data separation, schemas, redaction.
User URL: SSRF/private-network redirects -> no arbitrary server fetch in MVP.
Official APIs: stale/outage/schema drift -> source IDs, fetched_at, validation, expiry, explicit errors, no invented defaults.
LLM: hallucination/override/leakage -> grounding, narrow role, structured output, deterministic authority, unsupported-claim evaluation.
Browser session: token theft/fixation/CSRF -> 32-byte CSPRNG token, DB hash only, expiry, HttpOnly·SameSite Strict cookie, Secure in deployed environments.
Profile object access: guessed/shared UUID -> authenticated owner ID in every CRUD/metrics query, uniform 404 for missing and foreign-owned records.
Next proxy: unrelated cookie leakage -> forward only `finshield_session`; never log raw Cookie or financial request bodies.
## Security test backlog
Prompt-injection golden set; PII logging regression; malicious URL; oversized payload; stale provider; schema drift; unsupported financial claim benchmark.
