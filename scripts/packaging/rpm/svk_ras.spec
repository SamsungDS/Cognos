Name:           svk-ras
Version:        %svk_rpm_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK RAS feature
Requires:       svk-core, libtraceevent, perl-DBD-SQLite, mce-inject, perl-File-Find
License:        Samsung Internal

%global svk_install_dir %_prefix/local/svk/feature_modules/ras
# We can assume _topdir is set to "build/rpmbuild" dir in project root (set in build.sh)
%global svk_build_dir %_topdir/..
%global svk_script_dir %svk_build_dir/../scripts
%global svk_ras_ldconf ld.so.conf.d/svk-ras-%_arch.conf

%description
SVK RAS feature module & SVK RAS test tool.

%package devel
Summary:        SVK RAS devel package contains headers
Provides:       svk-ras-devel = %version
Requires:       svk-ras = %version svk-core

%description devel
SVK RAS downstream, upstream, and other related header files for app/feature development

%install
cd %svk_build_dir
# build commands go below
cmake -DWITH_RELEASE=ON -DPKG_CONFIG_PREFIX=%svk_install_dir -DCMAKE_INSTALL_PREFIX=%svk_install_dir ..
%make_install
%__mkdir_p %buildroot/%svk_install_dir

%files
%defattr(-,root,root,-)
%dir %svk_install_dir/
%svk_install_dir/%_lib
%svk_install_dir/include
%svk_install_dir/config
%svk_install_dir/adapters
%ghost %_sysconfdir/%svk_ras_ldconf

%files devel
%svk_install_dir/include

%post
# post-install commands go here
echo "%svk_install_dir/%_lib" > %_sysconfdir/%svk_ras_ldconf
%__chmod a+r %_sysconfdir/%svk_ras_ldconf
%_sbindir/ldconfig

# Create directory for rasdaemon sqlite db
mkdir -p /usr/local/var/lib/rasdaemon

# Add mce_inject kernel module to load across reboots
mkdir -p /usr/lib/modules-load.d

cat > /usr/lib/modules-load.d/svk-ras.conf  << EOF
# MCE Inject module required for SVK Cognos RAS
mce_inject
EOF

# Load the mce_inject module as one-time call
lsmod|grep mce_inject || modprobe mce_inject

%preun
# pre-uninstall commands go here

%postun
# post-uninstall commands go here
%_sbindir/ldconfig
rm -f /usr/lib/modules-load.d/svk-ras.conf
rmmod mce_inject

%changelog
* Wed Feb 5 2025 Mike Xu <pengfei.xu@samsung.com>
* Fri Sep 27 2024 Matt Durand <matt.d@samsung.com>
- Initial RPM spec which creates a release and a devel RPM. Devel RPM includes headers for feature development
