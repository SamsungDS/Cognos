FROM ubuntu:24.04

ADD scripts/dependencies /dependencies
RUN set -eux \
    && DOCKER=true /dependencies/install.sh \
    && rm -rf /dependencies
