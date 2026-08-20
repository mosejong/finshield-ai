# 12. Security Threat Model
## Assets
Financial profiles, fraud inputs, official product data, API credentials, prompts, results, evaluation/audit data.
## Trust boundaries
Client->API; API->official providers; API->model provider; API->DB/cache; evidence ingestion->retrieval.
## Threats & controls
User text: injection/oversize/PII -> limits, instruction-data separation, schemas, redaction. Implemented: `app/services/llm/untrusted.py` replaces only model-directed sentences with a placeholder before substitution, leaving user-directed scam imperatives byte-identical because they are the evidence the explanation stands on; `contradicts_verdict` in `validation.py` rejects reassuring output under a medium/high verdict; the verdict itself is computed before sanitization so no input filter can lower it.
User URL: SSRF/private-network redirects -> no arbitrary server fetch in MVP.
Official APIs: stale/outage/schema drift -> source IDs, fetched_at, validation, expiry, explicit errors, no invented defaults.
LLM: hallucination/override/leakage -> grounding, narrow role, structured output, deterministic authority, unsupported-claim evaluation.
Browser session: token theft/fixation/CSRF -> 32-byte CSPRNG token, DB hash only, expiry, HttpOnly·SameSite Strict cookie, Secure in deployed environments.
Profile object access: guessed/shared UUID -> authenticated owner ID in every CRUD/metrics query, uniform 404 for missing and foreign-owned records.
Next proxy: unrelated cookie leakage -> forward only `finshield_session`; never log raw Cookie or financial request bodies.
State-changing proxy requests: CSRF/cross-site form submission -> require an allowed `Origin`; reject missing or `Sec-Fetch-Site: cross-site` requests.
Public HTTP boundary: Host-header injection/TLS bypass/clickjacking -> explicit production trusted hosts, loopback-only internal ports, Caddy HTTPS-only public entry, CSP/frame denial/HSTS.
Observability: financial text/profile/session leakage and unbounded labels -> allowlisted structured fields only, route templates, no body/query/header logging, runtime secret non-disclosure test.
Unauthenticated API abuse: analyze CPU burn, unbounded anonymous session rows, oversized bodies -> per-IP rate limits with `429`+`Retry-After`, byte-counting body limits before schema validation at both the web proxy and the API, shared PostgreSQL counters, fail-open on counter-storage outage because blocking a fraud check is worse than a temporarily open limit.
Forged client address: `X-Forwarded-For` spoofing to escape or poison a rate-limit bucket -> count hops from the right, trust zero hops by default, edge proxy replaces rather than appends the chain, and chain trimming never shifts a right-anchored index.
Rate-limit counters as an access log: stored identifiers reversible for IPv4's 2^32 space -> HMAC bucket keys with a deployment secret, no identifier in failure logs, closed windows deleted by the retention job.
## Security test backlog
Prompt-injection golden set — done: `evaluation/data/injection_golden_v0.1.jsonl` (7 techniques) with offline assertions in `tests/test_llm_prompt_injection.py`; whether the model actually complies is a dated paid measurement in `docs/devlog/2026-08-20/prompt-injection-boundary.md` (2026-08-20, `gemini-3.6-flash`: 0 of 7 flipped the model with the defence off), not a CI check.
Remaining: PII logging regression; malicious URL; oversized payload; stale provider; schema drift; unsupported financial claim benchmark.
