Name:           svk-me
Version:        %svk_rpm_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK ME Plugin
License:        Samsung Internal
BuildRequires:  jansson
Requires:       svk-core, svk-mgmt-fw, jansson


%global svk_install_dir %_prefix/local/svk/feature_modules/me
# We can assume _topdir is set to "build/rpmbuild" dir in project root (set in build.sh)
%global svk_build_dir %_topdir/..
%global svk_script_dir %svk_build_dir/../scripts
%global svk_me_ldconf ld.so.conf.d/svk-me-%_arch.conf

%description
SVK Memory Engine - APIs and functions for application memory monitoring and management.

%install
cd %svk_build_dir
cmake -DWITH_RELEASE=ON -DCMAKE_CXX_IMPLICIT_INCLUDE_DIRECTORIES:STRING="/usr/include" \
        -DCMAKE_C_IMPLICIT_INCLUDE_DIRECTORIES:STRING="/usr/include" \
        -DCMAKE_INSTALL_PREFIX=%svk_install_dir ..
%make_install
# Remove the include directory and .h files
rm -rf %{buildroot}/usr/local/svk/feature_modules/me/include/

%files
%defattr(-,root,root,-)
%dir %svk_install_dir/
%svk_install_dir/%_lib
%svk_install_dir/config
%svk_install_dir/logic_modules
%ghost %_sysconfdir/%svk_me_ldconf

%post
echo "%svk_install_dir/%_lib" > %_sysconfdir/%svk_me_ldconf
%__chmod a+r %_sysconfdir/%svk_me_ldconf
%_sbindir/ldconfig

%postun
%_sbindir/ldconfig

%changelog
* Wed Jan 07 2026 Karthik Krishna <karthik1.k@samsung.com>
- Fix rpm packaging