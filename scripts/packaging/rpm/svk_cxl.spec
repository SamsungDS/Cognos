%if "%{mock_flag}" == "true"
Name:           svk-cxl-mock
%else
Name:           svk-cxl
%endif
Version:        %svk_cxl_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK CXL Plugin
License:        Samsung Internal
BuildRequires:  jansson
Requires:       svk-core, svk-mgmt-fw, jansson


%{!?installpath: %global installpath /usr/local/svk/cxl}
%{!?installpath_mgmt: %global installpath_mgmt /usr/local/svk/mgmt-fw}
%{!?installpath_mbox: %global installpath_mbox /usr/local/lib/cxl_memory_box}
%{!?installpath_zmq: %global installpath_zmq /etc/svk}
%{!?installpath_tm_config: %global installpath_tm_config /etc/svk}
%{!?cxl_build_dir: %global cxl_build_dir svk-cxl}
%{!?installpath_cmmh_lib: %global installpath_cmmh_lib /usr/local/lib}
%{!?installpath_cmmh_include: %global installpath_cmmh_include /usr/local/include}
%{!?installpath_cmmh_service: %global installpath_cmmh_service /etc/systemd/system}
%{!?installpath_cmmh_driver: %global installpath_cmmh_service /usr/local/bin}


%description
SVK CXL plugin to manage and access CXL devices.

# Always installing to /usr/local/svk/cxl for now
%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%{installpath}
mkdir -p %{buildroot}/%{installpath_mgmt}
mkdir -p %{buildroot}/%{installpath_mbox}/lib
mkdir -p %{buildroot}/%{installpath_zmq}
mkdir -p %{buildroot}/%{installpath_tm_config}
mkdir -p %{buildroot}/%{installpath_cmmh_lib}
mkdir -p %{buildroot}/%{installpath_cmmh_include}

# If rpmbuild is run in the build script, use CMAKE_INSTALL_PREFIX as temp dir in %{_topdir}/BUILD
%if "%{getenv:CMAKE_INSTALL_PREFIX}" != ""
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/%{_lib} %{buildroot}/%{installpath}
cp -rf %{_fmapilibpath} %{buildroot}/%{installpath_mbox}/lib
cp -f %{_fmapiincpath}/sample_json/input.json %{buildroot}/%{installpath_mgmt}
cp -f /etc/svk/zmq_config.json %{buildroot}/%{installpath_zmq}
cp -f /etc/svk/damo_config.json %{buildroot}/%{installpath_tm_config}
cp -f /etc/svk/tm_gen_config.py %{buildroot}/%{installpath_tm_config}
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/config/cxl.conf %{buildroot}/%{installpath_mgmt}
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/config/cxl_dev_id_map.json %{buildroot}/%{installpath_mgmt}
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/config/cxl_utils.py %{buildroot}/%{installpath_mgmt}
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/config/log.conf %{buildroot}/%{installpath_mgmt}
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/third_party/libcmmh.a %{buildroot}/%{installpath_cmmh_lib}/
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/third_party/libcmmh.h %{buildroot}/%{installpath_cmmh_include}/
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/third_party/cmmh_driver %{buildroot}/%{installpath_cmmh_driver}/
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/third_party/cmmh_driver.service %{buildroot}/%{installpath_cmmh_service}/
chmod 755 %{buildroot}/%{installpath_cmmh_driver}/cmmh_driver
chmod 644 %{buildroot}/%{installpath_cmmh_service}/cmmh_driver.service

# If rpmbuild is run manually, use default build dir svk-core, unless user gives a different name
%else
cp -rf %{cxl_build_dir}/%{_lib} %{buildroot}/%{installpath}
cp -rf %{_fmapipath} %{buildroot}/%{installpath_mbox}/lib
cp -f %{_fmapiincpath}/sample_json/input.json %{buildroot}/%{installpath_mgmt}
cp -f /etc/svk/zmq_config.json %{buildroot}/%{installpath_zmq}
cp -f /etc/svk/damo_config.json %{buildroot}/%{installpath_tm_config}
cp -f /etc/svk/tm_gen_config.py %{buildroot}/%{installpath_tm_config}
cp -f %{cxl_build_dir}/config/cxl.conf  %{buildroot}/%{installpath_mgmt}
cp -f %{cxl_build_dir}/config/cxl_dev_id_map.json  %{buildroot}/%{installpath_mgmt}
cp -f %{cxl_build_dir}/config/cxl_utils.py  %{buildroot}/%{installpath_mgmt}
cp -f %{cxl_build_dir}/config/log.conf  %{buildroot}/%{installpath_mgmt}
cp -f %{cxl_build_dir}/third_party/libcmmh.a %{buildroot}/%{installpath_cmmh_lib}/
cp -f %{cxl_build_dir}/third_party/libcmmh.h %{buildroot}/%{installpath_cmmh_include}/
cp -f %{cxl_build_dir}/third_party/cmmh_driver %{buildroot}/%{installpath_cmmh_driver}/
cp -f %{cxl_build_dir}/third_party/cmmh_driver.service %{buildroot}/%{installpath_cmmh_service}/
chmod 755 %{buildroot}/%{installpath_cmmh_driver}/cmmh_driver
chmod 644 %{buildroot}/%{installpath_cmmh_service}/cmmh_driver.service
%endif

%files
#%license add-license-file-here
#%doc add-docs-here
%defattr(-,root,root,-)
%{installpath}/%{_lib}
%{installpath_mgmt}
%{installpath_mbox}
%{installpath_zmq}
%{installpath_tm_config}
%{installpath_cmmh_lib}/libcmmh.a
%{installpath_cmmh_include}/libcmmh.h
%{installpath_cmmh_service}/cmmh_driver.service
%{installpath_cmmh_driver}/cmmh_driver

%clean

%post
# export the SVK_LDCONFIG if a separate install path was given
if [ -z "$SVK_LDCONFIG" ];then
    installpath="/usr/local/svk/cxl"
fi
touch /etc/ld.so.conf.d/svk-cxl-x86_64.conf
chmod a+r /etc/ld.so.conf.d/svk-cxl-x86_64.conf
echo "$installpath/%{_lib}" | tee -a /etc/ld.so.conf.d/svk-cxl-x86_64.conf
echo "/usr/local/lib/cxl_memory_box/lib" | tee -a /etc/ld.so.conf.d/svk-cxl-x86_64.conf
echo "/usr/local/svk/mgmt-fw/lib64" | tee -a /etc/ld.so.conf.d/svk-cxl-x86_64.conf
/usr/sbin/ldconfig

%postun
rm /etc/ld.so.conf.d/svk-cxl-x86_64.conf
rm -rf /usr/local/lib/cxl_memory_box 
rm -rf /usr/local/svk/cxl
/usr/sbin/ldconfig
