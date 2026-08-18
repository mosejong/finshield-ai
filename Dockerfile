FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system --gid 10001 finshield \
    && useradd --system --uid 10001 --gid finshield --home-dir /app finshield

WORKDIR /app

# 런타임 lock 만 복사한다. requirements-dev.txt 는 이미지에 들어가지 않으므로
# pytest 같은 개발 도구가 프로덕션 컨테이너에 실리지 않는다.
#
# --require-hashes: 모든 패키지가 == 로 고정되고 해시가 일치해야 설치된다.
# lock 에 빠진 전이 의존성이 있으면 조용히 넘어가지 않고 빌드가 실패한다.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.txt

COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts

USER finshield

EXPOSE 8000

# 워커 수를 CMD 에 박지 않는다. uvicorn 은 `--workers` 를 넘기지 **않았을 때만**
# 이 변수를 읽기 때문에(`uvicorn/config.py`: `if workers is None and
# "WEB_CONCURRENCY" in os.environ`), 플래그를 빼야 compose 가 호스트 크기에 따라
# 다른 값을 줄 수 있다. 값은 종전과 같은 2 이고, 1GB VM 은 여기를 1 로 내린다
# (`compose.yaml` 의 `FINSHIELD_UVICORN_WORKERS`, `docs/31` 11-6).
ENV WEB_CONCURRENCY=2

# `--timeout-worker-healthcheck` 를 기본 5초로 두지 않는다. 2026-08-18 GCP
# e2-micro 에서 이 기본값이 백엔드를 **영구적으로** 세웠다.
#
# uvicorn 은 워커가 2개 이상일 때만 `Multiprocess` 감시자를 쓴다(1개면
# `server.run()` 을 직접 부르고 감시자 자체가 없다). 이 감시자는 0.5초마다
# 자식에게 ping 을 보내고 `timeout_worker_healthcheck` 안에 답이 없으면
# SIGKILL 한 뒤 새 워커를 띄운다. 그런데 워커는 fork 가 아니라 **spawn** 이라
# (`uvicorn/_subprocess.py`) 매번 인터프리터가 처음부터 부팅되고, ping 에
# 답하는 스레드는 그 부팅이 끝난 뒤에야 생긴다. 기동 경합으로 그 창이 5초를
# 넘기면 부모가 자식을 죽이고 곧바로 새 인터프리터를 두 개 더 띄운다 - 경합이
# 원인인데 대응이 경합을 키우는 자기강화 루프다. SIGKILL 이라 트레이스백이
# 없어서 로그에는 "Waiting for child process" 와 "Child process died" 만
# 무한히 남는다.
#
# 30초인 이유: 컨테이너 healthcheck 가 5초 간격 12회로 약 60초 안에 판정한다.
# 그보다 짧게 두어야 진짜로 굳은 워커를 uvicorn 이 먼저 잡고, 느린 기동을
# 굳은 것으로 오판하지 않는다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-worker-healthcheck", "30", "--no-access-log"]
