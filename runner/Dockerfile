FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY runner ./runner
ENV PYTHONUNBUFFERED=1 EVAL_DATA_DIR=/data
EXPOSE 8080
CMD ["uvicorn", "runner.api:app", "--host", "0.0.0.0", "--port", "8080"]

# `docker build --target test` runs the unit tests (used by `make test`)
FROM base AS test
RUN pip install --no-cache-dir pytest httpx
COPY tests ./tests
RUN python -m pytest -q tests

# default target: the runtime image
FROM base AS runtime
