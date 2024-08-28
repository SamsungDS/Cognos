# SVK Core

## Description

SVK Core contains utilities and framework for [Management Framework](https://cxl-gitlab.ssi.samsung.com/dfs/svk/mgmt-fw) as well as other [SVK applications](https://cxl-gitlab.ssi.samsung.com/dfs/svk) to communicate with feature modules such as power throttling, [Converged Storage](https://cxl-gitlab.ssi.samsung.com/dfs/svk/converged), etc. Documentation for header files and APIs needed to add a feature module can be found on the [SVK Core Doxygen page](https://dfs.cxl-gitlab-pages.ssi.samsung.com/svk/core/). See [SVK Application/Feature module integration](#svk-applicationfeature-module-integration) for details related to integrating feature modules with SVK Core.

### Supported OS List

- Rockylinux 9
- Ubuntu 22.04

## Installation

The prefered method to install SVK Core is through your OS package manager.

SVK Core's CI/CD automatically produces release artifacts which are published to [SSG-Nexus](http://ssg-nexus.msl.lab:8081/), which you can browse from within the SSG lab network.

Release artifacts are also published to the [SVK Core Package Registry on Gitlab](https://cxl-gitlab.ssi.samsung.com/dfs/svk/core/-/packages).

Enable the SSG Nexus repo for your distro, then install the `svk-core` packages via the package manager:

### Ubuntu

```bash
wget --quiet --output-document /usr/share/keyrings/ssg-nexus.pgp  http://ssg-nexus.msl.lab:8081/repository/svk_common/public.pgp
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ssg-nexus.pgp] http://ssg-nexus.msl.lab:8081/repository/svk_apt_ubuntu22 $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ssg-nexus.list
apt update
apt-get install svk-core svk-core-dev -y

```

### Rockylinux

```bash
curl -fsSL http://ssg-nexus.msl.lab:8081/repository/svk_common/ssg-nexus-$(. /etc/os-release && echo "$ID${VERSION_ID%%.*}").repo -o /etc/yum.repos.d/ssg-nexus.repo
dnf install svk-core svk-core-devel -y
```

## Build & Installation

### Build Dependencies

Execute the dependencies installation script to install all build dependencies for your current OS:

```bash
./scripts/dependencies/install.sh
```

### Build SVK Core

[After installing build dependencies](#Build-Dependencies), execute the `./scripts/build.sh` script. The `-h` option will show what options are available for building SVK Core:

```bash
./scripts/build.sh -h
```

To build SVK Core, run unit tests and generate code coverage reports, execute:

```bash
./scripts/build.sh -t
```

To build and install SVK Core to a specified directory, execute:

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

- `svk-core`: Runtime files
- `svk-core-dev(el)`: Development header files


### Manual Build

To build the SVK Framework library without tests:

```bash
mkdir build
cd build
cmake3 ../  -DCMAKE_INSTALL_PREFIX=svk_fw_distrib --fresh
make install
```

In the above example, SVK Core is installed to the `build/svk_fw_distrib` directory.

### Unit Testing

To build the SVK Framework with tests (GTest) and code coverage, run the `cmake3` command with `-DBUILD_TESTING` and `-DWITH_COVERAGE` flags enabled:

```bash
mkdir build
cd build
cmake3 ../  -DBUILD_TESTING=ON -DWITH_COVERAGE=ON -DCMAKE_INSTALL_PREFIX=svk_fw_distrib --fresh
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

## SVK Application/Feature module integration

[Install SVK Core](#Installation) to install the necessary headers and libraries for feature modules to use.

This will install any headers and libs to `/usr/local/svk/core` for feature modules to use and link against.

### Using pkg-config to get flags needed for building with core

You can use the pkg-config file to get the necessary flags for building core.

Export the `PKG_CONFIG_PATH` variable with the location of the directory that contains `svkframework.pc` (should be your build directory by default) and run the `pkg-config` command. For example:

```bash
export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/usr/local/svk/core/lib64/pkgconfig

pkg-config --cflags svkframework -I/root/core/build/install_dir/include -DSPDLOG_COMPILED_LIB -DSPDLOG_FMT_EXTERNAL

pkg-config --libs svkframework -L/root/core/build/install_dir/lib64 -lspdlog -pthread -lfmt
```

You can use the cmake pkgconfig to easily access the installed dirs in your cmake file:

```cmake
find_package(PkgConfig REQUIRED)
pkg_check_modules(SVKFRAMEWORK REQUIRED svkframework)

# Following vars are for getting libs/dirs
${SVKFRAMEWORK_INCLUDE_DIRS}
${SVKFRAMEWORK_CFLAGS_OTHER}
${SVKFRAMEWORK_LIBRARY_DIRS}
${SVKFRAMEWORK_LIBRARIES}
```

## Integration testing

For integration testing, you must build SVK Framework with the install prefix option as shown in the build script example above. This is needed to put the header files and libraries for SVK Management framework to consume. Once that is built and the `include` and `lib64` directories in the install dir are populated with the appropriate headers and libs, follow the instructions for SVK Management Framework build and give `include` directory as part of the build flag and the `lib64` directory as a node server startup option. For example:

```text
--framework_lib_path ../core/build/install_dir/lib64/
```

Then run the client command to the GRPC server to test end to end functionality. At least one feature module must be loaded for this to work.

To use the sample feature module, build SVK Framework with tests and list the `build/tests/sample_feature` directory in the core config. This will call the sample feature module functions and validate if the client can call the feature functions. The sample feature module has the same ID as power throttle (feature_id 0).

## Usage

Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.
