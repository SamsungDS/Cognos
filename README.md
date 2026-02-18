# SVK RAS

## Description

SVK RAS is a feature module of SVK, providing the CXL memory related RAS functionality.

### Supported OS List

- Rockylinux 9
- Ubuntu 22.04
- Ubuntu 24.04

## Installation

The prefered method to install SVK RAS is through your OS package manager.

SVK RAS's CI/CD automatically produces release artifacts which are published to [SSG-Nexus](http://ssg-nexus.msl.lab:8081/), which you can browse from within the SSG lab network.

Release artifacts are also published to the [SVK RAS Package Registry on Gitlab](https://cxl-gitlab.ssi.samsung.com/dfs/svk/ras/-/packages).

Enable the SSG Nexus repo for your distro, then install the `svk-ras` packages via the package manager:

### Ubuntu

```bash
wget --quiet --output-document /usr/share/keyrings/ssg-nexus.pgp  http://ssg-nexus.msl.lab:8081/repository/svk_common/public.pgp
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ssg-nexus.pgp] http://ssg-nexus.msl.lab:8081/repository/svk_apt_ubuntu22 $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ssg-nexus.list
apt update
apt-get install svk-ras svk-ras-dev -y

```

### Rockylinux

```bash
curl -fsSL http://ssg-nexus.msl.lab:8081/repository/svk_common/ssg-nexus-$(. /etc/os-release && echo "$ID${VERSION_ID%%.*}").repo -o /etc/yum.repos.d/ssg-nexus.repo
dnf install epel-release -y
dnf install svk-ras svk-ras-devel -y
```

### Oracle Linux

```bash
source /etc/os-release
MAJOR_VER="${VERSION_ID%%.*}"
curl -fsSL http://ssg-nexus.msl.lab:8081/repository/svk_common/ssg-nexus-$(. /etc/os-release && echo "$ID${VERSION_ID%%.*}").repo -o /etc/yum.repos.d/ssg-nexus.repo
dnf install oracle-epel-release-el${MAJOR_VER} -y
dnf install svk-ras svk-ras-devel -y
```

## Build & Installation

### Build Dependencies

Execute the dependencies installation script to install all build dependencies for your current OS:

```bash
./scripts/dependencies/install.sh
```

### Build SVK RAS

[After installing build dependencies](#build-dependencies), execute the `./scripts/build.sh` script. The `-h` option will show what options are available for building SVK RAS:

```bash
./scripts/build.sh -h
```

To build SVK RAS, run unit tests and generate code coverage reports, execute:

```bash
./scripts/build.sh -t
```

To build and install SVK RAS to a specified directory, execute:

```bash
./scripts/build.sh -p install_dir
```

Note: Unless an absolute path is provided, the install path is relative to the `build` dir in the project root.

### Release build

To execute a release build, execute:

```bash
./scripts/build.sh -r
```

This will build and package RPM or Debian Packages (on Rockylinux or Ubuntu, respectively), which are staged in the `build/artifacts` dir in the project root. The packages produced include:

- `svk-ras`: Runtime files
- `svk-ras-dev(el)`: Development header files

### Manual Build

RAS manual build without tests:

```bash
mkdir build
cd build
cmake3 ../  -DCMAKE_INSTALL_PREFIX=svk_ras
make install
```

In the above example, SVK RAS is installed to the `build/svk_ras` directory.

### Unit Testing

To build the SVK RAS with tests (GTest) and code coverage, run the `cmake3` command with `-DBUILD_TESTING` and `-DWITH_COVERAGE` flags enabled:

```bash
mkdir build
cd build
cmake3 ../  -DBUILD_TESTING=ON -DWITH_COVERAGE=ON -DCMAKE_INSTALL_PREFIX=svk_fw_distrib
make install
```

Tests related files are generated in `build/tests`. To run the tests manually:

```bash
cd build/tests
ctest
```

This will produce an output of all the unit tests that are under the `tests/` directory. To run each test individually, run the unit test binary located in a similar path to where the unit test source code is. For example: `build/tests/unit/framework/src/framework_ut`. Note: if you don't run ctest as a user that has write/read privileges to the `/var` or `/etc` directories, some tests may fail.

To see the code coverage report for a source file, cd to the directory where the object files are located, ex. `build/framework/CMakeFiles/svkframework.dir/src`. Make sure the `.gcda` and `.gcno` files are there and run `gcovr` (must be installed with pip), giving the source code dir and current working dir as parameters:

```bash
cd build/framework/CMakeFiles/svkframework.dir/src
gcovr -r {path_to_source_code} .
```
