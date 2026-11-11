Name:           cognos-grpc
Version:        %{getenv:RPM_VERSION}
Release:        1%{?dist}
URL:            https://github.com/grpc/grpc
Summary:        SVK gRPC
# Since the grpc repo's abseil sub-repo is used,
# mark the standard abseil-cpp rpm as conflict
# TODO: Need to revert this back
# %if 0%{?rhel} == 9
Conflicts:      abseil-cpp-devel
# %endif
Requires:       c-ares-devel, zlib-devel
License:        Samsung Internal

%description
SVK gRPC

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -rf %{getenv:STAGING_DIR}/* %{buildroot}/

%files
%defattr(-,root,root,-)
%{_bindir}/*
%{_datadir}/*
%{_includedir}/*
/usr/lib/*
%{_libdir}/*

#%license add-license-file-here
#%doc add-docs-here

%clean
rm -rf %{buildroot}

%post

%postun

%changelog
* Wed Aug 07 2024 - Matt Durand <matt.d@samsung.com>
- Initial RPM spec for SVK gRPC
