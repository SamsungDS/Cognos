FROM rockylinux:9-minimal

ADD scripts/dependencies /dependencies
RUN set -eux \
    && DOCKER=true /dependencies/install.sh \
    && rm -rf /dependencies

COPY scripts/container_rt/rocky9_enable_gcc13.sh /usr/bin/rocky9_enable_gcc13.sh
ENV BASH_ENV="/usr/bin/rocky9_enable_gcc13.sh" \
        ENV="/usr/bin/rocky9_enable_gcc13.sh"
