# Cognos SLA Tracker Feature Module

## Description

Cognos SLA Tracker module is a feature loaded by the Cognos Core framework. Depending on the application requirements with resepect to the latency and other attributes, it sends the request to the underlying logic modules to execute the operation w.r.t the requirements. It collects the SLA details from the operation and sends to the upper module to validate the requirements and send the request to the underlying supporting modules to configure the devices to meet the SLA requirements.

### Supported OS List

- Rockylinux 9
- Ubuntu 22.04
- Ubuntu 24.04
- Oracle Linux 10

## Build

slat is built and tested with the rest of Cognos, from the repository root: see
[Build](../../README.md#build) (`./build.sh slat`, and `./build.sh --test slat` for its unit tests).

