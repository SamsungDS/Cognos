FROM ubuntu:22.04

ADD scripts/dependencies /dependencies
RUN set -eux \
    && /dependencies/install.sh \
    rm -rf /dependencies
