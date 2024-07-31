Name:           svk-cxl
Version:        %{getenv:GIT_VER}
Release:        1%{?dist}
Summary:        SVK CXL Plugin
License:        Samsung Internal

BuildRequires:  jansson jansson-devel
Requires:       svk-core
# Enable me
# Requires:       svk-mgmt-fw
Requires:       jansson jansson-devel

%{!?installpath: %global installpath /usr/local/svk/cxl}
%{!?cxl_build_dir: %global cxl_build_dir svk-cxl}


%description
SVK CXL plugin to manage and access CXL devices.

# Always installing to /usr/local/svk/cxl for now
%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%{installpath}

# If rpmbuild is run in the build script, use CMAKE_INSTALL_PREFIX as temp dir in %{_topdir}/BUILD
%if "%{getenv:CMAKE_INSTALL_PREFIX}" != ""
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/lib64 %{buildroot}/%{installpath}

# If rpmbuild is run manually, use default build dir svk-core, unless user gives a different name
%else
cp -rf %{cxl_build_dir}/lib64 %{buildroot}/%{installpath}
%endif

%files
#%license add-license-file-here
#%doc add-docs-here
%{installpath}/lib64

%clean
rm -rf %{buildroot}

%post
# export the SVK_LDCONFIG if a separate install path was given
if [ -z "$SVK_LDCONFIG" ];then
    installpath="/usr/local/svk/cxl"
fi
touch /etc/ld.so.conf.d/svk-cxl-x86_64.conf
chmod a+r /etc/ld.so.conf.d/svk-cxl-x86_64.conf
echo "$installpath/lib64" | tee -a /etc/ld.so.conf.d/svk-cxl-x86_64.conf
/usr/sbin/ldconfig

%postun
rm /etc/ld.so.conf.d/svk-cxl-x86_64.conf
/usr/sbin/ldconfig
