Name:           cognos-core
Version:        %svk_core_version
Release:        1%{?dist}.%svk_os_version
Summary:        Cognos core framework
Requires:       spdlog zeromq
License:        Samsung Internal

%global svk_core_svk_topdir %_prefix/local/svk
%global svk_core_feat_module_path %svk_core_svk_topdir/feature_modules
%global svk_core_install_dir %svk_core_svk_topdir/core
%global svk_core_pcfile pkgconfig/svkframework.pc
%global svk_core_ldconf ld.so.conf.d/svk-core-%_arch.conf

%description
Cognos API routing framework library for Cognos apps and feature modules.

%package devel
Summary:        Cognos core devel package contains headers and sample_feature
Provides:       cognos-core-devel = %version
Requires:       cognos-core = %version zeromq-devel spdlog-devel pkg-config

%description devel
Cognos downstream, upstream, and other related header files for app/feature development

%install
cd %svk_core_builddir
cmake -DWITH_RELEASE=ON -DPKG_CONFIG_PREFIX=%svk_core_install_dir -DCMAKE_INSTALL_PREFIX=%svk_core_install_dir -DFEAT_MODULE_PATH=%svk_core_feat_module_path ..
%make_install

%files
%defattr(-,root,root,-)
%dir %svk_core_svk_topdir/
%dir %svk_core_install_dir/
%svk_core_install_dir/%_lib/libsvkframework.so*
%svk_core_install_dir/%_lib/libsvklogger.so*
%svk_core_install_dir/%_lib/libsvkzmq.so*
%ghost %_sysconfdir/%svk_core_ldconf

%files devel
%ghost %_libdir/%svk_core_pcfile
%svk_core_install_dir/include
%svk_core_install_dir/tests
%svk_core_install_dir/%_lib/cmake
%svk_core_install_dir/%_lib/pkgconfig

%post
%__cat > %_sysconfdir/%svk_core_ldconf << EOF
%svk_core_install_dir/lib64
EOF
%__chmod a+r %_sysconfdir/%svk_core_ldconf
%_sbindir/ldconfig

%post devel
%__mkdir_p -v %_libdir/pkgconfig
%__ln_s -f %svk_core_install_dir/%_lib/%svk_core_pcfile %_libdir/%svk_core_pcfile

%postun
%_sbindir/ldconfig

%changelog
* Mon Jun 24 2024 Aaron Lee <a.lee03@samsung.com>
- Initial RPM spec which creates a release and a devel RPM. Devel RPM includes headers for feature development
