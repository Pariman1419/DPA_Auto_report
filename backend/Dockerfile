FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ARG APP_GIT_SHA=unknown
ENV APP_GIT_SHA=${APP_GIT_SHA}
LABEL org.opencontainers.image.revision=${APP_GIT_SHA}

EXPOSE 9090

# Disable reload for production; use 2 workers
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9090", "--workers", "2"]
