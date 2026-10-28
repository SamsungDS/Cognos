# ci-tools: the image of the plan, hygiene and registry jobs. It runs no
# component code. Phase 1 needs distribution packages only; changing this file
# changes the image tag (see gitlab/jobs/ci-tools-image.yml).
FROM ubuntu:24.04

RUN set -eux \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        python3 \
        python3-yaml \
        shellcheck \
    && rm -rf /var/lib/apt/lists/*
