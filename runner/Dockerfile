# Code runner: nsjail + CPython 3.12, stdlib-only HTTP front.
FROM debian:bookworm-slim AS nsjail
ARG NSJAIL_VERSION=3.4
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git make g++ pkg-config bison flex \
      protobuf-compiler libprotobuf-dev libnl-route-3-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${NSJAIL_VERSION}" https://github.com/google/nsjail.git /nsjail \
    && make -C /nsjail -j"$(nproc)" \
    && strip /nsjail/nsjail

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libprotobuf32 libnl-route-3-200 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=nsjail /nsjail/nsjail /usr/local/bin/nsjail
WORKDIR /srv
COPY bayt_runner ./bayt_runner
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RUNNER_WORKDIR=/sandbox \
    RUNNER_PYTHON=/usr/local/bin/python3
EXPOSE 8081
# The service itself runs as root only to set up namespaces; student code runs as
# uid 65534 inside and outside the jail (see bayt_runner/sandbox.py).
CMD ["python", "-m", "bayt_runner.server"]
