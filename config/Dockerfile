FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV TZ America/New_York
ENV C_FORCE_ROOT true
ENV UV_LINK_MODE=copy

WORKDIR /home/tjctgrader/autograder

RUN apt update && \
    apt install -y \
        bash \
        git \
        nodejs \
        npm \
        postgresql-server-dev-all \
        gcc \
        python3-dev \
        postgresql-client \
        libc6-dev \
        flex \
        bison \
        build-essential \
        protobuf-compiler \
        libprotobuf-dev \
        libnl-3-dev \
        libnl-route-3-dev \
        default-jdk \
        pkg-config

COPY nsjail nsjail
RUN cd nsjail && make && cd ..
RUN mv nsjail/nsjail /usr/bin
