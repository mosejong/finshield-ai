# FinShield Web

FinShield AI의 Next.js 16 프론트엔드다. 금융 계산이나 위험도 판정을 브라우저에서
다시 구현하지 않고 FastAPI의 결정론적 결과를 사용자 행동 중심 화면으로 표현한다.

## 실행

```bash
npm install
npm run dev
```

기본 주소는 `http://localhost:3000`이다. 실제 분석은 루트 저장소에서 FastAPI를
`http://127.0.0.1:8000`으로 실행해야 한다. 환경변수는 `.env.example`을 참고한다.

백엔드 없이 고정 예시 화면만 확인하려면 `NEXT_PUBLIC_API_MODE=mock`을 사용한다.
mock 결과는 화면에 예시로 표시되며 live 실패를 안전한 결과로 대체하지 않는다.

## 검증

```bash
npm run build
npx tsc --noEmit
npm run lint
npm test
```

## 주요 경로

- `/` — 금융 안전 홈
- `/onboarding` — 선택형 금융 프로필 입력
- `/profile` — 금융상태 확인
- `/check` — 의심 문구와 현재 상태 입력
- `/check/result/[id]` — Scenario Engine 결과, 행동, 공식 근거
- `/products` — 후속 상품 기능 자리표시

상세한 IA, 디자인 토큰, 계약과 안전 원칙은 `docs/13-frontend-architecture.md`에 있다.
