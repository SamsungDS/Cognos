Name:           cognos-me
Version:        %svk_rpm_version
Release:        1%{?dist}.%svk_os_version
Summary:        Cognos ME Plugin
License:        Samsung Internal
BuildRequires:  jansson
Requires:       cognos-core, cognos-mgmt-fw, jansson, libcgroup-original-tools, yaml-cpp, numactl


%global svk_install_dir %_prefix/local/svk/feature_modules/me
# We can assume _topdir is set to "build/rpmbuild" dir in project root (set in build.sh)
%global svk_build_dir %_topdir/..
%global svk_script_dir %svk_build_dir/../scripts
%global svk_me_ldconf ld.so.conf.d/svk-me-%_arch.conf
%global me_venv_dir /usr/local/svk/venv/me
%global me_venv_dir_amt2 /usr/local/svk/venv/me/amt2
%global amt2_scripts_dir %svk_install_dir/scripts/amt2_scripts
%global me_config_dir %svk_install_dir/config

%description
Cognos Memory Engine - APIs and functions for application memory monitoring and management.

%install
cd %svk_build_dir
cmake -DWITH_RELEASE=ON -DCMAKE_CXX_IMPLICIT_INCLUDE_DIRECTORIES:STRING="/usr/include" \
        -DCMAKE_C_IMPLICIT_INCLUDE_DIRECTORIES:STRING="/usr/include" \
        -DCMAKE_INSTALL_PREFIX=%svk_install_dir ..
%make_install
# Remove the include directory and .h files
rm -rf %{buildroot}/usr/local/svk/feature_modules/me/include/
%__mkdir_p %buildroot/%svk_install_dir/scripts/dependencies/python
%__mkdir_p %buildroot/%svk_install_dir/scripts/amt2_scripts

install -D -m 0644 %svk_script_dir/dependencies/python/requirements_deploy.txt %buildroot/%svk_install_dir/scripts/dependencies/python/
install -D -m 0644 %svk_script_dir/dependencies/python/requirements_deploy_amt_2.txt %buildroot/%svk_install_dir/scripts/dependencies/python/
install -m 0755 -t %buildroot/%svk_install_dir/scripts/amt2_scripts/ %svk_script_dir/amt2_scripts/*

%files
%defattr(-,root,root,-)
%dir %svk_install_dir/
%svk_install_dir/%_lib
%svk_install_dir/config
%svk_install_dir/logic_modules
%ghost %_sysconfdir/%svk_me_ldconf
%dir %svk_install_dir/scripts/
%dir %svk_install_dir/scripts/dependencies/
%dir %svk_install_dir/scripts/dependencies/python/
%svk_install_dir/scripts/dependencies/python/requirements_deploy.txt
%svk_install_dir/scripts/dependencies/python/requirements_deploy_amt_2.txt
%svk_install_dir/scripts/amt2_scripts/

%post
echo "%svk_install_dir/%_lib" > %_sysconfdir/%svk_me_ldconf
%__chmod a+r %_sysconfdir/%svk_me_ldconf
%_sbindir/ldconfig
echo "Creating the Python virtualenv ..."
# venv for amt 1.0 ; damo 2.7.0
/usr/bin/python3 -m venv %me_venv_dir
%me_venv_dir/bin/python3 -m pip install --upgrade pip
%me_venv_dir/bin/pip3 install -r %svk_install_dir/scripts/dependencies/python/requirements_deploy.txt
# venv for amt 2.0 ; damo 3.1.0
/usr/bin/python3 -m venv %me_venv_dir_amt2
%me_venv_dir_amt2/bin/python3 -m pip install --upgrade pip
%me_venv_dir_amt2/bin/pip3 install -r %svk_install_dir/scripts/dependencies/python/requirements_deploy_amt_2.txt

%preun
rm -f %amt2_scripts_dir/*_hot_fsrs.txt
rm -f %amt2_scripts_dir/hotness_map_results_*.log
rm -rf %amt2_scripts_dir/report_*/
rm -f %me_config_dir/global_damo_config.yaml

%postun
%_sbindir/ldconfig
rm -rf %me_venv_dir

%changelog
* Wed Jan 07 2026 Karthik Krishna <karthik1.k@samsung.com>
- Fix rpm packaging
