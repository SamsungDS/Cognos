Name:           svk-mgmt-fw
Version:        %{getenv:GIT_VER_FOR_RPM}
Release:        1%{?dist}
Summary:        SVK Management framework
Requires:       re2, svk-core, zeromq
License:        Samsung Internal

%{!?installpath: %global installpath /usr/local/svk/svk_mgmt_fw}
%{!?svk_mgmt_fw_build_dir: %global svk_mgmt_fw_build_dir svk-mgmt-fw}

%description
SVK Management framework related APIs, services

%package devel
Summary:        SVK Management framework devel package contains headers and sample_feature
Provides:       svk-mgmt-fw-devel = %{version}
Requires:       svk-core, svk-core-devel, svk-go-modules, svk-grpc, svk-mgmt-fw = %{version}

%description devel
SVK Management framework related API header files

# Always installing to /usr/local/svk/svk_mgmt_fw for now
%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%{installpath}

# If rpmbuild is run in the build script, use CMAKE_INSTALL_PREFIX as temp dir in %{_topdir}/BUILD
%if "%{getenv:CMAKE_INSTALL_PREFIX}" != ""
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/include %{buildroot}/%{installpath}
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/lib %{buildroot}/%{installpath}
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/lib64 %{buildroot}/%{installpath}
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/bin %{buildroot}/%{installpath}
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/rest_api %{buildroot}/%{installpath}
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/etc %{buildroot}/
# If rpmbuild is run manually, use default build dir svk-core, unless user gives a different name
%else
cp -rf %{svk_mgmt_fw_build_dir}/include %{buildroot}/%{installpath}
cp -rf %{svk_mgmt_fw_build_dir}/lib64 %{buildroot}/%{installpath}
cp -rf %{svk_mgmt_fw_build_dir}/lib %{buildroot}/%{installpath}
cp -rf %{svk_mgmt_fw_build_dir}/bin %{buildroot}/%{installpath}
cp -rf %{svk_mgmt_fw_build_dir}/rest_api %{buildroot}/%{installpath}
cp -rf %{svk_mgmt_fw_build_dir}/etc %{buildroot}/

%endif

%files
/etc
%{installpath}/lib
%{installpath}/lib64
%{installpath}/bin
%{installpath}/rest_api

#%license add-license-file-here
#%doc add-docs-here

%files devel
%{installpath}/include

%clean
rm -rf %{buildroot}

%post
# Encountering issues in the docker container since there is no support in docker
# Disabling for now
# systemctl daemon-reload

%postun

%changelog
* Mon Jul 25 2024 Suresh Grandhi <suresh.g@samsung.com>
- Initial RPM spec which creates a release and a devel RPM. Devel RPM includes headers for feature development
