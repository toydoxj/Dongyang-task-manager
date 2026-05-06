# dy-task-backend — FastAPI + WeasyPrint(한글 PDF) Docker 이미지.
# Render Web Service에서 runtime: docker로 사용. cron services는 별도 native Python.
FROM python:3.12-slim

# WeasyPrint 시스템 의존성 + 한글 폰트(Naver Nanum) 설치.
# fonts-nanum은 fontconfig 자동 등록 → CSS에서 'NanumGothic' 직접 사용 가능.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# lock 변경 없으면 dependency layer cache hit
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 앱 소스
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

ENV PYTHONUNBUFFERED=1

# alembic upgrade 후 uvicorn 실행. Render가 $PORT 자동 주입.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
