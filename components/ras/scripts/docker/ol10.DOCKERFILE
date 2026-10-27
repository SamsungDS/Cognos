FROM oraclelinux:10-slim

ADD scripts/dependencies /dependencies
RUN set -eux \
    && DOCKER=true /dependencies/install.sh \
    && rm -rf /dependencies