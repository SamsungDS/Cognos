Name:           svk-node
Version:        %svk_rpm_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK Node Information
Requires:       svk-core, lshw, numactl
License:        Samsung Internal

%global svk_install_dir %_prefix/local/svk/feature_modules/node
# We can assume _topdir is set to "build/rpmbuild" dir in project root (set in build.sh)
%global svk_build_dir %_topdir/..
%global svk_script_dir %svk_build_dir/../scripts
%global node_venv_dir /usr/local/svk/venv/node


%description
SVK Node feature module to get the node's information such as CPU, Memory, PCI devices etc.

%install
cd %svk_build_dir
# build commands go below
cmake -DWITH_RELEASE=ON -DPKG_CONFIG_PREFIX=%svk_install_dir -DCMAKE_INSTALL_PREFIX=%svk_install_dir ..
%make_install
%__mkdir_p %buildroot/%svk_install_dir
%__mkdir_p %buildroot/%svk_install_dir/scripts/dependencies/python

install -D -m 0644 %svk_script_dir/dependencies/python/requirements_deploy.txt %buildroot/%svk_install_dir/scripts/dependencies/python/


%files
%defattr(-,root,root,-)
# dir for svk/node - we can assume "svk" already exists because it is owned by core RPM
%dir %svk_install_dir/
%svk_install_dir/%_lib
%svk_install_dir/scripts
%svk_install_dir/config

%post
%__chmod a+x %svk_install_dir/scripts/*

echo "Creating the Python virtualenv ..."
# Create python venv on the deployment machine
/usr/bin/python3 -m venv %node_venv_dir
# Ensure pip is latest
%node_venv_dir/bin/python3 -m pip install --upgrade pip
# Install the dependencies
%node_venv_dir/bin/pip3 install -r %svk_install_dir/scripts/dependencies/python/requirements_deploy.txt

%preun
# pre-uninstall commands go here

%postun
%_sbindir/ldconfig
rm -rf %node_venv_dir

%changelog
* Sat Feb 17 2024 Suresh Grandhi <suresh.g@samsung.com>
- Initial RPM spec which creates a release and a devel RPM.
