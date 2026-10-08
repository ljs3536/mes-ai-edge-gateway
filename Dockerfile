FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Seoul

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY gateway ./gateway

RUN useradd --uid 10001 --no-create-home app
USER app

CMD ["python", "-m", "gateway"]
