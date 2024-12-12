Name:           svk-slat
Version:        %svk_rpm_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK SLA Tracker feature
Requires:       svk-core
License:        Samsung Internal

%global svk_install_dir %_prefix/local/svk/feature_modules/slat
# We can assume _topdir is set to "build/rpmbuild" dir in project root (set in build.sh)
%global svk_build_dir %_topdir/..
%global svk_script_dir %svk_build_dir/../scripts
%global svk_slat_ldconf ld.so.conf.d/svk-slat-%_arch.conf

%description
SVK SLA Tracker feature module

%install
cd %svk_build_dir
# build commands go below
cmake -DWITH_RELEASE=ON -DPKG_CONFIG_PREFIX=%svk_install_dir -DCMAKE_INSTALL_PREFIX=%svk_install_dir ..
%make_install
%__mkdir_p %buildroot/%svk_install_dir

%files
%defattr(-,root,root,-)
# dir for svk/template - we can assume "svk" already exists because it is owned by core RPM
%dir %svk_install_dir/
%svk_install_dir/%_lib
%svk_install_dir/config
%svk_install_dir/logic_modules
%ghost %_sysconfdir/%svk_slat_ldconf

%post
echo "%svk_install_dir/%_lib" > %_sysconfdir/%svk_slat_ldconf
%__chmod a+r %_sysconfdir/%svk_slat_ldconf
%_sbindir/ldconfig

%preun
# pre-uninstall commands go here

%postun
%_sbindir/ldconfig

%changelog
* Fri Oct 10 2024 Suresh Grandhi <suresh.g@samsung.com>
- Initial RPM spec which creates a release and a devel RPM.
