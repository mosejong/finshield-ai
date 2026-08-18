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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]
