FROM ubuntu:jammy

ADD scripts/dependencies /dependencies
RUN set -eux \
    && /dependencies/install.sh \
    rm -rf /dependencies