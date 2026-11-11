# Cognos

Cognos is the Samsung management console for CXL memory devices and tiered memory. It discovers the CXL devices
attached to a cluster's application servers, reports their state, health and errors, and lets an administrator
configure them from one place, through a REST API or a web user interface. On each server it profiles how
applications use memory and moves data between the faster tier (local DRAM) and the slower tier (CXL or remote
memory) to meet each application's service-level requirements.

A Cognos cluster has a management server, which runs the controller and the REST API, and one or more application
servers, which run a node agent and the feature modules that work with the hardware. This repository holds the whole
Cognos software stack, its build, its CI and its deployment.

## Features

The features are the components of the Cognos stack. Each one is built into its own package (`cognos-<name>`), and
all of them carry the one Cognos version.

#### Cognos Core

The framework that every other component builds on. It provides inter-process communication and publish/subscribe
messaging between the services and the feature modules, and the loader that finds and starts the feature modules at
run time. Its headers and libraries are published for the other components through pkg-config.

#### Cognos Management Framework

The management layer of a Cognos cluster. It contains the gRPC controller that runs on the management server, the
node server that runs on every application server and registers with the controller, the REST API server, and the
service manager that loads the feature modules on each node. It also holds the gRPC API definitions (proto files)
shared by the components.

#### Cognos CXL

The feature module for CXL devices. It reads and updates the state of the connected CXL memory devices through their
fabric management interface, and reports it upward to the controller and the user interface. It can run against real
devices or, in its mock variant (`cognos-cxl-mock`), against simulated ones for development and testing.

#### Cognos SLA Tracker

The feature module that keeps applications within their service-level agreements. Depending on an application's
requirements, such as latency, it sends each operation to the logic modules that can meet them, collects the SLA
details of the result, and asks the supporting modules to configure the devices when the requirements are not met.

#### Cognos RAS

The feature module for reliability, availability and serviceability of CXL memory. It collects and handles the
memory errors and events the system reports for CXL devices, so that the controller and the user interface can show
the health of each device and act on failures.

#### Cognos Memory Engine

The feature module for tier-aware data placement. It profiles how an application uses its memory and moves data
between the faster tier (DRAM) and the slower tier (CXL or remote memory) according to what it finds. Profilers and
data movers are pluggable logic modules, configured per application.

#### Cognos Node

The feature module that describes each server: its CPUs, its memory and its PCI devices. The controller, the other
feature modules and the user interface use this information to know what each application server has, and the user
interface shows it per node.

#### Cognos App

The Cognos management application, the top layer of the stack. It provides the backend of the web application, which
talks to the Cognos services, stores state and metadata and passes Cognos events to the user interface; a subscriber
that stores the published metrics in InfluxDB; the web user interface, served by Caddy; and an optional RBAC service
for user accounts and roles.

## Profilers

#### AMO-Prof

AMO-Prof is a profiling and report-generation tool for AI inference workloads. It correlates the metrics of the
serving framework (SGLang and its HiCache KV cache) with GPU and HBM telemetry, host DRAM bandwidth, operating-system
memory pressure, network and local storage activity, and produces HTML reports (executive summary, interactive
timelines and a detailed end report) that show where a workload's bottleneck is across HBM, DRAM and SSD. It is a
standalone Python package with its own version and is not part of the Cognos packages. See the
[AMO-Prof README](profilers/amo-prof/README.md).

## Repository layout

| Path | Contents |
|---|---|
| `features/` | The Cognos components: `core`, `mgmt-fw`, `cxl`, `slat`, `ras`, `me`, `node`. |
| `apps/sapp` | The Cognos management application: backend, user interface and RBAC service. |
| `profilers/amo-prof` | The AMO-Prof profiler. |
| `cama` | CaMa (coming soon). |
| `deploy/ansible/` | The Ansible playbooks and roles that deploy Cognos, and the deployment scripts. |
| `utils/` | Utilities (empty for now). |
| `ci/` | The CI scripts that do not depend on GitLab: version, images, dev sets, compatibility check. |
| `gitlab/` | The GitLab CI configuration and its scripts. See [docs/ci.md](docs/ci.md). |
| `docs/` | Documentation of the CI. |
| `build.sh` | Builds the packages of the components, or runs their unit tests. |
| `VERSION` | The release line of the Cognos stack (`MAJOR.MINOR`). |
| `LICENSE` | The Apache License, Version 2.0. |
| `NOTICE` | The copyright notice. |

Each component keeps its own `README.md` and its own `scripts/build.sh`.

## Build

#### Cognos

`build.sh` at the repository root builds the release packages (`.deb` for Ubuntu 24.04, `.rpm` for Oracle Linux 10)
of all the components, in dependency order, and collects them in `build/artifacts/<os>/`:

```bash
./build.sh                       # all components for Ubuntu 24.04, each in a Docker container
./build.sh --os ol10             # the same for Oracle Linux 10
./build.sh core mgmt-fw          # only these components
./build.sh --mock cxl            # the cxl mock variant (cognos-cxl-mock)
./build.sh --test                # run the components' unit tests instead of building packages
```

Each component is built in a container from its own `scripts/docker/<os>.DOCKERFILE`. Those images install their
build dependencies from the internal Nexus, so this needs the lab network. With `--native`, `build.sh` builds on the
current machine instead, which must run the target OS and have the component's dependencies installed
(`scripts/dependencies/install.sh` in the component's folder). `./build.sh -h` shows all options.

The packages get the version printed by `ci/version.sh`: the `vX.Y.Z` tag on the current commit, otherwise a
development version of the next release line (for example `1.7.0~dev.0.local`). How the pipeline builds, tests and
publishes the packages is described in [docs/ci.md](docs/ci.md).

#### AMO-Prof

AMO-Prof is a Python package (Python 3.12 or later). From `profilers/amo-prof`, either build a wheel:

```bash
cd profilers/amo-prof
scripts/build_wheel.sh           # -> dist/amoprof-<version>-py3-none-any.whl
python3 -m venv ~/amoprof_venv && source ~/amoprof_venv/bin/activate
pip install dist/amoprof-*.whl
amoprof --version
```

or install it from the source tree together with the operating-system tools its collectors use:

```bash
cd profilers/amo-prof
./install.sh
source ~/amoprof_venv/bin/activate
amoprof --version
```

[profilers/amo-prof/README.md](profilers/amo-prof/README.md) describes the options and the collectors' tools.

## Deploy

Cognos is deployed with Ansible. The playbooks, roles and the steps to follow, from setting up the Ansible
controller to running the deployment and setting the passwords it needs, are in
[deploy/ansible/README.md](deploy/ansible/README.md).

## Papers and publications

- [Samsung Cognos Management Console white paper](https://download.semiconductor.samsung.com/resources/white-paper/04_01_Latest_Samsung_Cognos_Mgmt_Console_Whitepaper_10139392999591.pdf)

## License

Copyright 2026 Samsung Electronics Co., Ltd.

Cognos is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
