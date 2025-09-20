FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV TZ America/New_York
ENV C_FORCE_ROOT true
ENV UV_LINK_MODE=copy

RUN apt update && \
    apt install -y bash git postgresql-server-dev-all gcc python3-dev postgresql-client libc6-dev

WORKDIR /home/tjctgrader/autograder