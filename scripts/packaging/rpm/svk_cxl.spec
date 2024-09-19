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
%{!?cxl_build_dir: %global cxl_build_dir svk-cxl}


%description
SVK CXL plugin to manage and access CXL devices.

# Always installing to /usr/local/svk/cxl for now
%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%{installpath}
mkdir -p %{buildroot}/%{installpath}/share/cxl_memory_box/lib
mkdir -p %{buildroot}/%{installpath}/conf

# If rpmbuild is run in the build script, use CMAKE_INSTALL_PREFIX as temp dir in %{_topdir}/BUILD
%if "%{getenv:CMAKE_INSTALL_PREFIX}" != ""
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/%{_lib} %{buildroot}/%{installpath}
cp -rf %{_fmapilibpath} %{buildroot}/%{installpath}/share/cxl_memory_box/lib
cp -f %{_fmapiincpath}/sample_json/input.json %{buildroot}/%{installpath}/conf

# If rpmbuild is run manually, use default build dir svk-core, unless user gives a different name
%else
cp -rf %{cxl_build_dir}/%{_lib} %{buildroot}/%{installpath}
cp -rf %{_fmapipath} %{buildroot}/%{installpath}/share/cxl_memory_box/lib
cp -f %{_fmapiincpath}/sample_json/input.json %{buildroot}/%{installpath}/conf
%endif

%files
#%license add-license-file-here
#%doc add-docs-here
%defattr(-,root,root,-)
%{installpath}/%{_lib}
%{installpath}/share/
%{installpath}/conf


%clean
# rm -rf %{buildroot}

%post
# export the SVK_LDCONFIG if a separate install path was given
if [ -z "$SVK_LDCONFIG" ];then
    installpath="/usr/local/svk/cxl"
fi
touch /etc/ld.so.conf.d/svk-cxl-x86_64.conf
chmod a+r /etc/ld.so.conf.d/svk-cxl-x86_64.conf
echo "$installpath/%{_lib}" | tee -a /etc/ld.so.conf.d/svk-cxl-x86_64.conf
mkdir -p /usr/local/lib/cxl_memory_box
cp -rf %{installpath}/share/cxl_memory_box /usr/local/lib
cp -f %{buildroot}/%{installpath}/conf/input.json /usr/local/svk/mgmt-fw/
echo "/usr/local/lib/cxl_memory_box/lib" | tee -a /etc/ld.so.conf.d/svk-cxl-x86_64.conf
/usr/sbin/ldconfig


%postun
rm /etc/ld.so.conf.d/svk-cxl-x86_64.conf
rm -rf /usr/local/lib/cxl_memory_box 
/usr/sbin/ldconfig
