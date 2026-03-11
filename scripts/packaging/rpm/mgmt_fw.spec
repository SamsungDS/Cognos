Name:           cognos-mgmt-fw
Version:        %svk_rpm_version
Release:        1%{?dist}.%svk_os_version
Summary:        Cognos Management framework
Requires:       re2, cognos-core, zeromq
License:        Samsung Internal

%global svk_install_dir %_prefix/local/svk/mgmt-fw
# We can assume _topdir is set to "build/rpmbuild" dir in project root (set in build.sh)
%global svk_build_dir %_topdir/..
%global svk_script_dir %svk_build_dir/../scripts

%description
Cognos Management framework related APIs, services

%package devel
Summary:        Cognos Management framework devel package contains headers and sample_feature
Provides:       cognos-mgmt-fw-devel = %version
Requires:       cognos-mgmt-fw = %version

%description devel
Cognos downstream, upstream, and other related header files for app/feature development

%install
cd %svk_build_dir
cmake -DWITH_RELEASE=ON -DPKG_CONFIG_PREFIX=%svk_install_dir -DCMAKE_INSTALL_PREFIX=%svk_install_dir ..
%make_install

# Rest API Build
%__mkdir_p %buildroot/%svk_install_dir/rest_api
go mod tidy -C %svk_build_dir/rest_api/tests
# Build svk_rest_server with svk_short_version var (passed from build.sh)
go build -C %svk_build_dir/rest_api/tests/cmd/app -o %buildroot/%svk_install_dir/rest_api/svk_rest_server-%svk_short_version
# Set svk_rest_server symlink
%__ln_s svk_rest_server-%svk_short_version %buildroot/%svk_install_dir/rest_api/svk_rest_server

# Install systemd scripts
install -D -m 0644 %svk_script_dir/systemd_files/svk-controller.service %buildroot/%_unitdir/cognos-controller.service
install -D -m 0644 %svk_script_dir/systemd_files/svk-node.service %buildroot/%_unitdir/cognos-node.service
install -D -m 0644 %svk_script_dir/systemd_files/svk-restserver.service %buildroot/%_unitdir/cognos-restserver.service
install -D -m 0644 %svk_script_dir/systemd_files/svk-svc-mgr.service %buildroot/%_unitdir/cognos-svc-mgr.service

%files
%defattr(-,root,root,-)
# dir for svk/mgmt-fw - we can assume "svk" already exists because it is owned by core RPM
%dir %svk_install_dir/
%svk_install_dir/%_lib
%svk_install_dir/bin
%svk_install_dir/rest_api
%_unitdir/cognos-controller.service
%_unitdir/cognos-node.service
%_unitdir/cognos-restserver.service
%_unitdir/cognos-svc-mgr.service
%_sysconfdir/svk/mgmt_fw_config.json
%_sysconfdir/svk/device_sla_config.json.example
%ghost %_sysconfdir/ld.so.conf.d/svk-mgmt-fw-%_arch.conf

%files devel
%svk_install_dir/include

%post
echo "%svk_install_dir/%_lib" > %_sysconfdir/ld.so.conf.d/svk-mgmt-fw-%_arch.conf
%__chmod a+r %_sysconfdir/ld.so.conf.d/svk-mgmt-fw-%_arch.conf
%_sbindir/ldconfig
%systemd_post cognos-controller.service
%systemd_post cognos-node.service
%systemd_post cognos-restserver.service
%systemd_post cognos-svc-mgr.service

%preun
%systemd_preun cognos-controller.service
%systemd_preun cognos-node.service
%systemd_preun cognos-restserver.service
%systemd_preun cognos-svc-mgr.service 

%postun
%_sbindir/ldconfig
%systemd_postun_with_restart cognos-controller.service
%systemd_postun_with_restart cognos-node.service
%systemd_postun_with_restart cognos-restserver.service
%systemd_postun_with_restart cognos-svc-mgr.service 

%changelog
* Mon Jun 24 2024 Suresh Grandhi <suresh.g@samsung.com>
- Initial RPM spec which creates a release and a devel RPM. Devel RPM includes headers for feature development
