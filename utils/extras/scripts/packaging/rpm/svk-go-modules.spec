Name:           cognos-go-modules
Version:        %{getenv:RPM_VERSION}
Release:        1%{?dist}
URL:            https://github.com/grpc-ecosystem/grpc-gateway
Summary:        SVK Go Modules
Requires:       golang
License:        Samsung Internal

%define _prefix /usr/local

%description
SVK Go Modules for gRPC and protobuf

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -rf %{getenv:STAGING_DIR}/* %{buildroot}/

%files
%defattr(-,root,root,-)
%{_prefix}/*

#%license add-license-file-here
#%doc add-docs-here

%clean
rm -rf %{buildroot}

%post

%postun

%changelog
* Wed Aug 07 2024 - Matt Durand <matt.d@samsung.com>
- Initial RPM spec for SVK Go Modules
