#!/bin/bash

Name:           svk-app
Version:        %{svk_rpm_version}
Release:        1%{?dist}.%{svk_os_version}
Summary:        Samsung Cognos Management Console
License:        Samsung Internal

# Build tools
BuildRequires: systemd-rpm-macros nodejs npm

# Runtime dependencies
Requires: systemd python3 nodejs npm libgfortran libquadmath docker-ce-cli caddy

%global debug_package %{nil}
%global __strip /bin/true
%global __brp_strip /bin/true
%global __brp_strip_static_archive /bin/true
%global __os_install_post %{nil}
%global svk_install_dir %_prefix/local/svk/svk-app

%description
Samsung Cognos Management Console


%build
# create SCMC_VERSION file
%{_projectdir}/scripts/get_version.sh > %{_projectdir}/cognos/SCMC_VERSION
# Clean install Cognos UI dependencies
npm --prefix %{_projectdir}/cognos/ui ci
# build react code into static bundle
npm --prefix %{_projectdir}/cognos/ui run build


%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
STATIC_REACT_PATH=%{buildroot}/var/www/scmc
CADDY_PATH=%{buildroot}/etc/caddy/Caddyfile.d
INSTALL_PATH=%{buildroot}/usr/local/svk/svk-app
FINAL_PATH=/usr/local/svk/svk-app
BUILDROOT_PREFIX=${INSTALL_PATH}

mkdir -p ${INSTALL_PATH}

# Setup Caddy
mkdir -p ${STATIC_REACT_PATH}
mkdir -p ${CADDY_PATH}
cp -a %{_projectdir}/cognos/ui/build/. ${STATIC_REACT_PATH}/
cp %{_projectdir}/scmc.conf ${CADDY_PATH}/

# copying CAL files
mkdir -p -v ${INSTALL_PATH}/cognos/backend/config/
cp %{_projectdir}/cognos/backend/*.py ${INSTALL_PATH}/cognos/backend/; 2>/dev/null
cp %{_projectdir}/cognos/backend/VERSION ${INSTALL_PATH}/cognos/backend/; 2>/dev/null
cp %{_projectdir}/cognos/backend/config/*.json ${INSTALL_PATH}/cognos/backend/config/; 2>/dev/null

# copying subscriber files
mkdir -p -v ${INSTALL_PATH}/cognos/subscriber/
cp %{_projectdir}/cognos/subscriber/*.py ${INSTALL_PATH}/cognos/subscriber/; 2>/dev/null
cp %{_projectdir}/cognos/subscriber/*.output ${INSTALL_PATH}/cognos/subscriber/; 2>/dev/null
cp %{_projectdir}/cognos/subscriber/*.json ${INSTALL_PATH}/cognos/subscriber/; 2>/dev/null

# copying python requirements file
cp %{_projectdir}/scripts/dependencies/python/requirements.txt ${INSTALL_PATH}/requirements.txt

# copying SCMC version file
cp %{_projectdir}/cognos/SCMC_VERSION ${INSTALL_PATH}

# copying RBAC files
mkdir -p -v ${INSTALL_PATH}/cognos/rbac/
mkdir -p ${INSTALL_PATH}/cognos/rbac/core/bin
mkdir -p ${INSTALL_PATH}/cognos/rbac/core/etc
mkdir -p ${INSTALL_PATH}/cognos/rbac/ssl
mkdir -p ${INSTALL_PATH}/cognos/rbac/core/lib
cp %{_projectdir}/cognos/rbac/rbac-docker-build-by-os.sh ${INSTALL_PATH}/cognos/rbac/
cp %{_projectdir}/cognos/rbac/ubuntu_Dockerfile ${INSTALL_PATH}/cognos/rbac/
cp %{_projectdir}/cognos/rbac/oel_Dockerfile ${INSTALL_PATH}/cognos/rbac/
cp %{_projectdir}/cognos/rbac/docker-config.env ${INSTALL_PATH}/cognos/rbac/
cp %{_projectdir}/cognos/rbac/docker-env-setup.sh ${INSTALL_PATH}/cognos/rbac/
cp %{_projectdir}/cognos/rbac/ecosystem.config.js ${INSTALL_PATH}/cognos/rbac/
cp -r %{_projectdir}/cognos/rbac/core/bin/rbac-client-repo ${INSTALL_PATH}/cognos/rbac/core/bin/
cp -r %{_projectdir}/cognos/rbac/core/bin/rbac-service ${INSTALL_PATH}/cognos/rbac/core/bin/
cp %{_projectdir}/cognos/rbac/core/etc/rbac.yaml ${INSTALL_PATH}/cognos/rbac/core/etc/
cp -r %{_projectdir}/cognos/rbac/core/bin/rbac-service/rbac-module ${INSTALL_PATH}/cognos/rbac/core/bin/rbac-service/
cp %{_projectdir}/cognos/rbac/core/etc/ports.txt ${INSTALL_PATH}/cognos/rbac/core/etc/
cp %{_projectdir}/cognos/rbac/core/etc/version.txt ${INSTALL_PATH}/cognos/rbac/core/etc/
cp %{_projectdir}/cognos/rbac/core/etc/rbac_*.json ${INSTALL_PATH}/cognos/rbac/core/etc/
cp -r %{_projectdir}/cognos/rbac/core/lib/licensing ${INSTALL_PATH}/cognos/rbac/core/lib/

# copying Telegraf files
mkdir -p -v ${INSTALL_PATH}/cognos/telegraf
cp -r %{_projectdir}/cognos/telegraf/* ${INSTALL_PATH}/cognos/telegraf/

# copy/install systemd services
mkdir -p %{buildroot}%{_unitdir}
install -d %{buildroot}%{_unitdir}
install -m 0644 %{_projectdir}/scripts/services/cognos-app.service           %{buildroot}%{_unitdir}/cognos-app.service
install -m 0644 %{_projectdir}/scripts/services/cognos-subscriber.service    %{buildroot}%{_unitdir}/cognos-subscriber.service
install -m 0644 %{_projectdir}/scripts/services/cognos-rbac.service          %{buildroot}%{_unitdir}/cognos-rbac.service

# copy/install cognos.config
install -m 0644 %{_projectdir}/scripts/cognos.config ${INSTALL_PATH}/cognos.config

%files
# requirements file
%{svk_install_dir}/requirements.txt
# top level config file
%{svk_install_dir}/cognos.config
# SCMC VERSION FILE
%{svk_install_dir}/SCMC_VERSION
# Caddy files
%dir /var/www/
%dir /var/www/scmc/
/var/www/scmc/*
/etc/caddy/Caddyfile.d/scmc.conf
# source code
%dir %{svk_install_dir}/
%{svk_install_dir}/*
%dir %{svk_install_dir}/cognos/backend/
%{svk_install_dir}/cognos/backend/*
%dir %{svk_install_dir}/cognos/backend/config/
%{svk_install_dir}/cognos/backend/config/*
%dir %{svk_install_dir}/cognos/subscriber/
%{svk_install_dir}/cognos/subscriber/*
%dir %{svk_install_dir}/cognos/rbac/
%{svk_install_dir}/cognos/rbac/*
%dir %{svk_install_dir}/cognos/rbac/core/bin/
%{svk_install_dir}/cognos/rbac/core/bin/*
%dir %{svk_install_dir}/cognos/rbac/core/bin/rbac-service/
%{svk_install_dir}/cognos/rbac/core/bin/rbac-service/*
%dir %{svk_install_dir}/cognos/rbac/core/etc/
%{svk_install_dir}/cognos/rbac/core/etc/*
%dir %{svk_install_dir}/cognos/rbac/core/lib/
%{svk_install_dir}/cognos/rbac/core/lib/*
%dir %{svk_install_dir}/cognos/telegraf/
%{svk_install_dir}/cognos/telegraf/*
# systemd units
%{_unitdir}/cognos-app.service
%{_unitdir}/cognos-subscriber.service
%{_unitdir}/cognos-rbac.service

%post
set -e

APPDIR=/usr/local/svk/svk-app
VENV=$APPDIR/env
REQ=$APPDIR/requirements.txt
WHEELS=$APPDIR/scripts/dependencies/python/wheels

# install UI deps
pushd ${APPDIR}/cognos/ui
npm install
popd

# setup python venv and install dependencies
if [ ! -x "$VENV/bin/python" ]; then
    /usr/bin/python3 -m venv --upgrade-deps "$VENV"
fi

# upgrade pip tooling inside of venv
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel

# install dependencies
if [ -d "$WHEELS" ] && [ "$(ls -A "$WHEELS" 2>/dev/null)" ]; then
    # offline install
    "$VENV/bin/python" -m pip install --no-index --find-links "$WHEELS" -r "$REQ"
else
    # online install
    "$VENV/bin/python" -m pip install -r "$REQ"
fi

# import scmc conf to Caddy
CADDYFILE=/etc/caddy/Caddyfile
IMPORT_LINE='import /etc/caddy/Caddyfile.d/*'

if [ ! -f "$CADDYFILE" ]; then
    echo "$IMPORT_LINE" > "$CADDYFILE"
else
    if ! grep -qF "$IMPORT_LINE" "$CADDYFILE"; then
        echo "" >> "$CADDYFILE"
        echo "$IMPORT_LINE" >> "$CADDYFILE"
    fi
fi

chown -R caddy:caddy ${STATIC_REACT_PATH}
chmod -R a+rX ${STATIC_REACT_PATH}

%systemd_post cognos-app.service
%systemd_post cognos-subscriber.service
%systemd_post cognos-rbac.service

%preun
%systemd_preun cognos-app.service
%systemd_preun cognos-subscriber.service
%systemd_preun cognos-rbac.service
if [ $1 -eq 0 ]; then
    rm -rf /usr/local/svk/svk-app
fi

%postun
%systemd_postun_with_restart cognos-app.service
%systemd_postun_with_restart cognos-subscriber.service
%systemd_postun_with_restart cognos-rbac.service

%changelog
* Wed Mar 19 2026 Nadim Sarras <nadim.s@samsung.com>
- SCMC Production Grade Webserver Packaging
* Wed Feb 04 2026 Nadim Sarras <nadim.s@samsung.com>
- Initial RPM packaging for OEL10