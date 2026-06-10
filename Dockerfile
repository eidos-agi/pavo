FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY pavo ./pavo

RUN pip install --no-cache-dir .

CMD ["pavo-worker"]
