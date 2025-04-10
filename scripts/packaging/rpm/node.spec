Name:           svk-node
Version:        %svk_rpm_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK Node Information
Requires:       svk-core
License:        Samsung Internal

%global svk_install_dir %_prefix/local/svk/feature_modules/node
# We can assume _topdir is set to "build/rpmbuild" dir in project root (set in build.sh)
%global svk_build_dir %_topdir/..
%global svk_script_dir %svk_build_dir/../scripts

%description
SVK Node feature module to get the node's information such as CPU, Memory, PCI devices etc.

%package devel
Summary:        SVK node devel package contains headers and sample_feature
Provides:       svk-node-devel = %version
Requires:       svk-node = %version, svk-core-devel

%description devel
SVK Node feature's devel module provides the headers and other development libraries

%install
cd %svk_build_dir
# build commands go below
cmake -DWITH_RELEASE=ON -DPKG_CONFIG_PREFIX=%svk_install_dir -DCMAKE_INSTALL_PREFIX=%svk_install_dir ..
%make_install
%__mkdir_p %buildroot/%svk_install_dir

%files
%defattr(-,root,root,-)
# dir for svk/node - we can assume "svk" already exists because it is owned by core RPM
%dir %svk_install_dir/
%svk_install_dir/%_lib


%files devel
# devel files go here

%post
# post-install commands go here

%preun
# pre-uninstall commands go here

%postun
# post-uninstall commands go here

%changelog
* Wed Feb 17 2024 Suresh Grandhi <suresh.g@samsung.com>
- Initial RPM spec which creates a release and a devel RPM.
