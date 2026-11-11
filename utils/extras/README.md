# Extras

Third-party packages that Cognos builds against, built from their public sources at the versions Cognos uses:

- `cognos-grpc`: gRPC 1.59.2 C++ libraries, with its re2 library;
- `cognos-go-modules`: the protobuf and gRPC Go code generators (protoc-gen-go v1.36.0, protoc-gen-go-grpc v1.5.1,
  protoc-gen-grpc-gateway and protoc-gen-openapiv2 v2.25.1).

mgmt-fw, cxl and me build against them.

## Build

They are built with the rest of Cognos, first, from the repository root: see [Build](../../README.md#build)
(`./build.sh extras`).
