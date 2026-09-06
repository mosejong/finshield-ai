# ADR 색인

아키텍처·신뢰 경계·데이터 수집 범위를 바꾸는 결정은 여기에 ADR로 남긴다.

**다음 번호: 0008** — 새 ADR을 쓰기 전에 이 줄을 먼저 확인하고, 파일을 만든 뒤 이 표와 번호를 함께 갱신한다. 번호는 한 번 배정하면 재사용하지 않는다.

| 번호 | 제목 | 상태 | 결정일 |
|---|---|---|---|
| 0001 | [Hybrid Decision Architecture](0001-hybrid-decision-architecture.md) | Accepted for MVP | 2026-08-11 |
| 0002 | [FinancialProfile 암호화 영속화](0002-encrypted-profile-persistence.md) | Accepted | 2026-08-13 |
| 0003 | [익명 세션 profile 소유권](0003-anonymous-session-profile-ownership.md) | Accepted | 2026-08-13 |
| 0004 | [익명 데이터 보존·정리](0004-anonymous-data-lifecycle.md) | Accepted | 2026-08-13 |
| 0005 | [Same-origin 상태 변경 보호와 HTTPS 진입점](0005-http-security-and-https-boundary.md) | 승인 | 2026-08-13 |
| 0006 | [Privacy-safe observability](0006-privacy-safe-observability.md) | 승인 | 2026-08-13 |
| 0007 | [합성 bootstrap fraud evaluation을 먼저 고정한다](0007-bootstrap-fraud-evaluation.md) | Accepted | 2026-08-13 |
| 0007 | [Minimum Financial Data Collection](0007-minimum-financial-data.md) | Accepted for MVP | 2026-08-11 |

**0007 은 두 문서가 함께 쓰고 있다** — 표의 마지막 두 행이다. `0007-minimum-financial-data.md` 는 2026-08-11 결정이지만 번호는 2026-08-14 에 재배정됐다. 처음 `0002` 로 만들어졌다가 `0002-encrypted-profile-persistence.md` 와 번호가 겹쳤고, 0003–0006 이 이미 암호화 ADR 을 0002 로 두고 이어졌기 때문에 뒤쪽 번호를 새로 받았다. **그때 `0007-bootstrap-fraud-evaluation.md`(2026-08-13)가 이미 0007 을 쓰고 있다는 것이 확인되지 않았다.** 위의 "번호는 재사용하지 않는다" 규칙에 어긋나는 상태이고, 개명하려면 이 번호를 참조하는 문서 네 곳을 함께 고쳐야 해서 공모전 심사가 끝난 뒤로 미룬다. 새 ADR 은 0008 부터 쓴다. 따라서 번호 순서와 결정일 순서는 0007 에서만 어긋난다.
