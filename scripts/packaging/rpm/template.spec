Name:           svk-template
Version:        %svk_rpm_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK Management framework
Requires:       svk-core
License:        Samsung Internal

%global svk_install_dir %_prefix/local/svk/template
# We can assume _topdir is set to "build/rpmbuild" dir in project root (set in build.sh)
%global svk_build_dir %_topdir/..
%global svk_script_dir %svk_build_dir/../scripts

%description
SVK Template description goes here

%package devel
Summary:        SVK Template devel package contains headers and sample_feature
Provides:       svk-template-devel = %version
Requires:       svk-template = %version

%description devel
SVK Template devel description goes here

%install
cd %svk_build_dir
# build commands go below
# cmake -DWITH_RELEASE=ON -DPKG_CONFIG_PREFIX=%svk_install_dir -DCMAKE_INSTALL_PREFIX=%svk_install_dir ..
# %make_install
%__mkdir_p %buildroot/%svk_install_dir
echo "foo" > %buildroot/%svk_install_dir/bar

%files
%defattr(-,root,root,-)
# dir for svk/template - we can assume "svk" already exists because it is owned by core RPM
%dir %svk_install_dir/
%svk_install_dir/bar

%files devel
# devel files go here

%post
# post-install commands go here

%preun
# pre-uninstall commands go here

%postun
# post-uninstall commands go here

%changelog
* Fri Sep 27 2024 Matt Durand <matt.d@samsung.com>
- Initial RPM spec which creates a release and a devel RPM.
