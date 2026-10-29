%if "%{mock_flag}" == "true"
Name:           cognos-cxl-mock
%else
Name:           cognos-cxl
%endif
Version:        %svk_cxl_version
Release:        1%{?dist}.%svk_os_version
Summary:        Cognos CXL Plugin
License:        Samsung Internal
BuildRequires:  jansson
Requires:       cognos-core, cognos-mgmt-fw, jansson, pciutils >= 3.10.0, dstat, python3

%package devel
Summary:        Cognos CXL devel package contains headers
Provides:       cognos-cxl-devel = %version
Requires:       cognos-cxl = %version

%description
Cognos CXL plugin to manage and access CXL devices.

%description devel
Cognos CXL downstream, upstream, and other related header files for app/feature development

%{!?installpath: %global installpath /usr/local/svk/cxl}
%{!?installpath_mgmt: %global installpath_mgmt /usr/local/svk/mgmt-fw}
%{!?cxl_build_dir: %global cxl_build_dir cognos-cxl}
%{!?installpath_cmmh_lib: %global installpath_cmmh_lib /usr/local/lib}
%{!?installpath_cmmh_include: %global installpath_cmmh_include /usr/local/include}
%{!?installpath_cmmh_service: %global installpath_cmmh_service /usr/lib/systemd/system}
%{!?installpath_cmmh_driver: %global installpath_cmmh_driver /usr/local/bin}
%{!?installpath_zmq: %global installpath_zmq /etc/svk}
%{!?installpath_tm_config: %global installpath_tm_config /etc/svk}
%global svk_install_dir %_prefix/local/svk/feature_modules/cxl
%global svk_build_dir %_topdir/..
%global cxl_venv_dir /usr/local/svk/venv/cxl


# Always installing to /usr/local/svk/cxl for now
%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%{installpath}
mkdir -p %{buildroot}/%{installpath_mgmt}
mkdir -p %{buildroot}/%{installpath_cmmh_lib}
mkdir -p %{buildroot}/%{installpath_cmmh_include}
mkdir -p %{buildroot}/%{installpath_zmq}
mkdir -p %{buildroot}/%{installpath_tm_config}


# If rpmbuild is run in the build script, use CMAKE_INSTALL_PREFIX as temp dir in %{_topdir}/BUILD

#Run cmake
cd %svk_build_dir
cmake -DWITH_RELEASE=ON -DPKG_CONFIG_PREFIX=%svk_install_dir -DCMAKE_INSTALL_PREFIX=%svk_install_dir ..
%make_install
%__mkdir_p %buildroot/%svk_install_dir

%files
#%license add-license-file-here
#%doc add-docs-here
%defattr(-,root,root,-)
%dir %svk_install_dir/
%svk_install_dir/config
%svk_install_dir/scripts/cxl_device_info.py
%svk_install_dir/scripts/dependencies/python/requirements_deploy.txt
%svk_install_dir/logic_modules
%{installpath_mgmt}
%{installpath_cmmh_lib}/libcmmh.a
%{installpath_cmmh_service}/cmmh_driver.service
%attr(0755, root, root) %{installpath_cmmh_driver}/cmmh_driver
%{installpath_zmq}
%{installpath}/%{_lib}
/etc/ld.so.conf.d/svk-cxl-x86_64.conf
%exclude %svk_install_dir/lib64/cmake
%exclude %svk_install_dir/lib64/pkgconfig

%files devel
%svk_install_dir/include
%svk_install_dir/lib64/cmake
%svk_install_dir/lib64/pkgconfig
%{installpath_cmmh_include}/libcmmh.h

%clean

%post
# export the SVK_LDCONFIG if a separate install path was given
if [ -z "$SVK_LDCONFIG" ];then
    installpath="/usr/local/svk/cxl"
fi
touch /etc/ld.so.conf.d/svk-cxl-x86_64.conf
chmod a+r /etc/ld.so.conf.d/svk-cxl-x86_64.conf
chmod +x %svk_install_dir/scripts/cxl_device_info.py
echo "$installpath/%{_lib}" | tee -a /etc/ld.so.conf.d/svk-cxl-x86_64.conf
echo "/usr/local/svk/mgmt-fw/lib64" | tee -a /etc/ld.so.conf.d/svk-cxl-x86_64.conf
/usr/sbin/ldconfig

MGMT_DIR="/usr/local/svk/mgmt-fw"
CXL_CONFIG_DIR="/usr/local/svk/feature_modules/cxl/config"

mkdir -p "$MGMT_DIR"

for file in input.json cxl.conf cxl_dev_id_map.json log.conf cxl_utils.py; do
  if [ ! -e "$MGMT_DIR/$file" ]; then
    ln -sf "$CXL_CONFIG_DIR/$file" "$MGMT_DIR/$file"
  fi
done

echo "Creating the Python virtualenv ..."
# venv for damo and tm_gen_config.py
/usr/bin/python3 -m venv %cxl_venv_dir
%cxl_venv_dir/bin/python3 -m pip install --upgrade pip
%cxl_venv_dir/bin/pip3 install -r %svk_install_dir/scripts/dependencies/python/requirements_deploy.txt

%postun
# Remove venv only on uninstall, not on upgrade
if [ $1 -eq 0 ]; then
  rm -rf %cxl_venv_dir
fi
rm -f /etc/ld.so.conf.d/svk-cxl-x86_64.conf
rm -rf /usr/local/svk/cxl
/usr/sbin/ldconfig

MGMT_DIR="/usr/local/svk/mgmt-fw"

for file in input.json cxl.conf cxl_dev_id_map.json log.conf cxl_utils.py; do
  if [ ! -e "$MGMT_DIR/$file" ]; then
    rm "$MGMT_DIR/$file"
  fi
done

%changelog
* Tue Jan 20 2026 FSL-JIRA@ssi.samsung.com
- Initial RPM spec which creates a release and a devel RPM for Cognos-CXL. Devel RPM includes headers for feature development

