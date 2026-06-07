# syntax=docker/dockerfile:1.7
#Stage 1: Build stage
FROM python:3.12-slim AS builder
ARG APPLICATION
ARG MICROSERVICE
# Install uv inside the builder container
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /code
# Copy only the configuration files first to maximize Docker layer caching
COPY ${APPLICATION}/pyproject.toml ${APPLICATION}/uv.lock ./
# Install dependencies into a synchronized deployment state
# --no-install-project prevents installing your local app code as an editable package yet
RUN uv sync --frozen --no-install-project --no-dev

# If this build targets the CA-enabled app, inject local CA cert into trust store.
RUN --mount=type=bind,source=utilities,target=/tmp/utilities,ro \
    if [ "$APPLICATION" = "fetcher" ]; then \
        cp /tmp/utilities/ca.crt ./ca.crt; \
        cp /tmp/utilities/check_and_append_cacert.py ./check_and_append_cacert.py; \
        uv run check_and_append_cacert.py; \
    fi

# --- Stage 2: Final lightweight production stage ---
FROM python:3.12-slim
ARG APPLICATION
ARG MICROSERVICE
WORKDIR /code
# Copy the pre-compiled virtual environment from the builder stage
COPY --from=builder /code/.venv /code/.venv
# Copy your actual application source code
COPY shared/ ./shared/
COPY ${APPLICATION}/${MICROSERVICE}*.py ./
# Expose the health port for Kubernetes liveness/readiness probes
# EXPOSE 10255
# Ensure the app uses the virtual environment's binaries automatically, and set Python to unbuffered mode for better logging in container environments
ENV PATH="/code/.venv/bin:$PATH" \
    PYTHONPATH="/code/shared" \
    PYTHONUNBUFFERED=1 \
    ARG=${MICROSERVICE}.py

# Run your application
CMD ["sh", "-c", "python /code/${ARG}"]