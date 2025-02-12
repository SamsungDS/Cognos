Name:           svk-core
Version:        %svk_core_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK core framework
Requires:       spdlog zeromq
License:        Samsung Internal

%global svk_core_svk_topdir %_prefix/local/svk
%global svk_core_install_dir %svk_core_svk_topdir/core
%global svk_core_pcfile pkgconfig/svkframework.pc
%global svk_core_ldconf ld.so.conf.d/svk-core-%_arch.conf

%description
SVK API routing framework library for SVK apps and feature modules.

%package devel
Summary:        SVK core devel package contains headers and sample_feature
Provides:       svk-core-devel = %version
Requires:       svk-core = %version zeromq-devel spdlog-devel

%description devel
SVK downstream, upstream, and other related header files for app/feature development

%install
cd %svk_core_builddir
cmake -DWITH_RELEASE=ON -DPKG_CONFIG_PREFIX=%svk_core_install_dir -DCMAKE_INSTALL_PREFIX=%svk_core_install_dir ..
%make_install

%files
%defattr(-,root,root,-)
%dir %svk_core_svk_topdir/
%dir %svk_core_install_dir/
%svk_core_install_dir/%_lib
%ghost %_libdir/%svk_core_pcfile
%ghost %_sysconfdir/%svk_core_ldconf

%files devel
%svk_core_install_dir/include
%svk_core_install_dir/tests

%post
%__cat > %_sysconfdir/%svk_core_ldconf << EOF
%svk_core_install_dir/lib
%svk_core_install_dir/lib64
EOF
%__chmod a+r %_sysconfdir/%svk_core_ldconf
%__mkdir_p -v %_libdir/pkgconfig
%__ln_s -f %svk_core_install_dir/%_lib/%svk_core_pcfile %_libdir/%svk_core_pcfile
%_sbindir/ldconfig

%postun
%_sbindir/ldconfig

%changelog
* Mon Jun 24 2024 Aaron Lee <a.lee03@samsung.com>
- Initial RPM spec which creates a release and a devel RPM. Devel RPM includes headers for feature development
