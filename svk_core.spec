Name:           svk-core
Version:        %{getenv:GIT_VER}
Release:        1%{?dist}
Summary:        SVK core framework
Requires:       spdlog
License:        Samsung Internal

%{!?installpath: %global installpath /usr/local/svk/core}
%{!?core_build_dir: %global core_build_dir svk-core}


%description
SVK API routing framework library for SVK apps and feature modules.

%package devel
Summary:        SVK core devel package contains headers and sample_feature
Provides:       svk-core-devel = %{version}

%description devel
SVK downstream, upstream, and other related header files for app/feature development

# Always installing to /usr/local/svk/core for now
%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/%{installpath}

# If rpmbuild is run in the build script, use CMAKE_INSTALL_PREFIX as temp dir in %{_topdir}/BUILD
%if "%{getenv:CMAKE_INSTALL_PREFIX}" != ""
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/include %{buildroot}/%{installpath}
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/lib64 %{buildroot}/%{installpath}
cp -rf %{getenv:CMAKE_INSTALL_PREFIX}/tests/sample_feature %{buildroot}/%{installpath}

# If rpmbuild is run manually, use default build dir svk-core, unless user gives a different name
%else
cp -rf %{core_build_dir}/include %{buildroot}/%{installpath}
cp -rf %{core_build_dir}/lib64 %{buildroot}/%{installpath}
cp -rf %{core_build_dir}/tests/sample_feature %{buildroot}/%{installpath}
%endif

%files
#%license add-license-file-here
#%doc add-docs-here
%{installpath}/lib64

%files devel
%{installpath}/include
%{installpath}/sample_feature

%clean
rm -rf %{buildroot}

%post
# export the SVK_LDCONFIG if a separate install path was given
if [ -z "$SVK_LDCONFIG" ];then
    installpath="/usr/local/svk/core"
fi
touch /etc/ld.so.conf.d/svk-core-x86_64.conf
chmod a+r /etc/ld.so.conf.d/svk-core-x86_64.conf
echo "$installpath/lib64" | tee -a /etc/ld.so.conf.d/svk-core-x86_64.conf
/usr/sbin/ldconfig

%postun
rm /etc/ld.so.conf.d/svk-core-x86_64.conf
/usr/sbin/ldconfig

%changelog
* Mon Jun 24 2024 Aaron Lee <a.lee03@samsung.com>
- Initial RPM spec which creates a release and a devel RPM. Devel RPM includes headers for feature development
