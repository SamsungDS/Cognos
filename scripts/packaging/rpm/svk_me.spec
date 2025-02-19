Name:           svk-me
Version:        %svk_me_version
Release:        1%{?dist}.%svk_os_version
Summary:        SVK ME Plugin
License:        Samsung Internal
BuildRequires:  jansson
Requires:       svk-core, svk-mgmt-fw, jansson


%{!?installpath: %global installpath /usr/local/svk/me}
%{!?installpath_mgmt: %global installpath_mgmt /usr/local/svk/mgmt-fw}
%{!?installpath_tm_config: %global installpath_tm_config /etc/svk}
%{!?me_build_dir: %global me_build_dir me}


%description
SVK Memory Engine - APIs and functions for application memory monitoring and management.

# Always installing to /usr/local/svk/me for now
%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%{installpath}
mkdir -p %{buildroot}/%{installpath_mgmt}
mkdir -p %{buildroot}/%{installpath_tm_config}

# If rpmbuild is run in the build script, use CMAKE_INSTALL_PREFIX as temp dir in %{_topdir}/BUILD
%if "%{getenv:CMAKE_INSTALL_PREFIX}" != ""
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/%{_lib} %{buildroot}/%{installpath}
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/damo_config.json %{buildroot}/%{installpath_tm_config}
cp -f %{getenv:CMAKE_INSTALL_PREFIX}/tm_gen_config.py %{buildroot}/%{installpath_tm_config}

# If rpmbuild is run manually, use default build dir svk-core, unless user gives a different name
%else
cp -rf %{me_build_dir}/%{_lib} %{buildroot}/%{installpath}
cp -f %{me_build_dir}/config/damo_config.json %{buildroot}/%{installpath_tm_config}
cp -f %{me_build_dir}/tools/tm_gen_config.py %{buildroot}/%{installpath_tm_config}
%endif

%files
#%license add-license-file-here
#%doc add-docs-here
%defattr(-,root,root,-)
%{installpath}/%{_lib}
%{installpath_mgmt}
%{installpath_tm_config}

%clean

%post
# export the SVK_LDCONFIG if a separate install path was given
if [ -z "$SVK_LDCONFIG" ];then
    installpath="/usr/local/svk/me"
fi
touch /etc/ld.so.conf.d/svk-me-x86_64.conf
chmod a+r /etc/ld.so.conf.d/svk-me-x86_64.conf
echo "$installpath/%{_lib}" | tee -a /etc/ld.so.conf.d/svk-me-x86_64.conf
echo "/usr/local/svk/mgmt-fw/lib64" | tee -a /etc/ld.so.conf.d/svk-me-x86_64.conf
/usr/sbin/ldconfig

%postun
rm /etc/ld.so.conf.d/svk-me-x86_64.conf
rm -rf /usr/local/svk/me
/usr/sbin/ldconfig
