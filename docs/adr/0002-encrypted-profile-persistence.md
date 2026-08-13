# ADR 0002: FinancialProfile 암호화 영속화

- 상태: Accepted
- 결정일: 2026-08-13
- 범위: `FinancialProfile` 저장 경계

## 배경

기존 저장소는 단일 프로세스 메모리에만 profile을 보관한다. 서버 재시작과 다중
worker에서 데이터가 사라지며 공개 배포에 사용할 수 없다. profile은 실명·주민번호·
계좌번호를 받지 않지만 소득·자산·부채 금액을 포함하므로 DB 운영자나 백업 유출에서
평문 노출을 줄여야 한다.

## 결정

1. 운영 DB는 PostgreSQL, ORM은 SQLAlchemy 2.x, migration은 Alembic을 사용한다.
2. 검증된 `FinancialProfile` 전체 JSON을 Fernet 인증 암호화한 뒤 하나의
   `encrypted_profile` binary column에 저장한다.
3. 암호화 키는 `PROFILE_ENCRYPTION_KEYS` 환경변수에서만 읽고 DB·로그·저장소에
   기록하지 않는다.
4. 첫 번째 키를 신규 쓰기 활성 키로 사용하고 각 row에는 비밀이 아닌 key ID만
   저장한다. 이전 키를 뒤에 유지해 순환 교체 중 기존 row를 읽을 수 있다.
5. production·staging 같은 배포 환경은 `postgresql+psycopg` URL과 암호화 키가
   모두 없거나 한쪽만 있으면 시작을 거부한다. development·test에서 둘 다 없을
   때만 기존 메모리 저장소를 허용한다.
6. 공개 API 응답과 profile 계산 계약은 바꾸지 않는다.

## 보안 경계

- Fernet은 암호문 기밀성과 변조 탐지를 함께 제공한다.
- DB에는 profile 검색용 평문 금융 필드를 만들지 않는다. 향후 검색이 필요하면 목적,
  최소 필드, 누출 위험을 별도 ADR로 검토한다.
- 키가 유출되면 DB 암호화만으로 보호할 수 없다. 운영에서는 secret manager, 접근
  통제, 키 순환, 백업 암호화가 추가로 필요하다.
- 이 결정은 전송구간 TLS, 사용자 인증·소유권, DB 볼륨 암호화, 감사로그를 대체하지
  않는다.

## 결과

- 장점: 재시작·다중 worker 영속성, DB dump의 금융정보 평문 노출 방지, 변조 탐지,
  명시적 migration과 키 순환 기반을 얻는다.
- 비용: profile 내부 필드 SQL 검색을 할 수 없고 키 분실 시 복구할 수 없다.
- 후속: 인증·소유권 컬럼은 별도 migration으로 추가하고, 기존 key ID row를 활성 키로
  재암호화하는 운영 명령을 구현한다.
