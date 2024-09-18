Name:           svk-app
Version:        %svk_rpm_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK Application
Requires:       svk-core
License:        Samsung Internal


%global svk_install_dir %_prefix/local/svk/app
# We can assume _topdir is set to "build/rpmbuild" dir in project root (set in build.sh)
%global svk_project_root %_topdir/../..
%global svk_script_dir %svk_project_root/scripts


%description
SVK Application


%install
# Create SVK Application directory
%__mkdir_p %buildroot/%svk_install_dir

# Set version of Cognos UI (React App)
%global svk_cognos_version $(%svk_script_dir/get_version.sh)
npm --prefix %svk_project_root/cognos/ui version %svk_cognos_version --allow-same-version

# Clean install Cognos UI dependencies
npm --prefix %svk_project_root/cognos/ui ci

# Build release Cognos UI (React App)
BUILD_PATH=%buildroot/%svk_install_dir/cognos-ui npm --prefix %svk_project_root/cognos/ui run build


%files
%defattr(-,root,root,-)
# dir for svk/app - we can assume "svk" already exists because it is owned by core RPM
%dir %svk_install_dir/
%svk_install_dir/cognos-ui


%post
# Post install TODO


%preun
# Pre-uninstall TODO


%postun
# Post-uninstall TOOD


%changelog
* Mon Jun 24 2024 Nadim Sarras <nadim.s@samsung.com>
- Initial RPM spec.
