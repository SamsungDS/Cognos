# SVK Core



## Description
SVK Core contains utilities and framework for Management framework or other SVK applications to communicate to the feature modules such as power throttling, Converged storage, etc. To see documentation on the header files and APIs that are needed to add a feature module, take a look at the [doxygen page](https://dfs.cxl-gitlab-pages.ssi.samsung.com/svk/core/) for SVK Core. For what is needed for feature modules to integrate with core, see [SVK Application/Feature module integration](#svk-applicationfeature-module-integration). More information will be added to it as necessary

## Build & Installation
Build has only been tested on CentOS Stream 8 and Rocky Linux 8. Requirements are cmake 3.7 for build w/out tests, cmake 3.14 for building with tests, and a C++ compiler compatible with C++17. Note: installing and using `gcc-toolset-11` should make the build process relatively easy.

There are two options for building, using the build script or using cmake to build manually.


### Dependencies
Run the `install.sh` script in `scripts/dependencies`. This will install dependencies for core building.

### Build script
Run the install script in the `scripts/dependencies` folder to install the dependencies needed for building. Run the `build.sh` script from the top level directory. The `-h` option will show what options are available for building SVK Framework.

    Build script for SVK Framework

    Syntax: build.sh [-t|c|h|p|r|f]
    options:
    -t | --build-tests
      Build the unit tests for SVK Framework.
    -c | --with-coverage
      Build with code coverage report. Must build unit tests for this.
    -h | --help
      Print this help.
    -p | --install-prefix
      Install libraries and related files to specified dir.
    -r | --release
      Release build. Generates a tarball called svk-core-<version>.tgz by default.
    -f | --filename
    Filename prefix to use for release tarball. Only applicable when building with release flag.

If you would like to build SVK Framework and run unit testing and generate code coverage reports for example, this is the command:

    ./scripts/build.sh -t -c

To build and install necessary artifacts to a specified directory, this is the command:

    ./scripts/build.sh -p install_dir


### Release build

To do a release build, use the `-r` flag. This will install the artifacts to `usr/local/svk` in the build directory and create a tarball called `svk-core-<version number>.tar.gz`. The tarball will contain the framework related headers/libs, as well as the sample feature module in case it is needed for testing.

### Manual Build
To build the SVK Framework library without tests:

    cd svk-core
    mkdir build
    cd build
    cmake3 ../  -DCMAKE_INSTALL_PREFIX=svk_fw_distrib  --fresh  && make install

All the distribution files goes into `build/svk_fw_distrib` directory

### Unit Testing
To build the SVK Framework with tests (GTest) and code coverage, run the above command with the `-DBUILD_TESTING` and `-DWITH_COVERAGE` flags enabled:

    cmake3 ../  -DBUILD_TESTING=ON -DWITH_COVERAGE=ON -DCMAKE_INSTALL_PREFIX=svk_fw_distrib --fresh
    make install

Tests related files are generated at `build/tests`. To run the tests:

    cd build/tests
    ctest

This will produce an output of all the unit tests that are under the `tests/` directory. To run each test individually, run the unit test binary located in a similar path to where the unit test source code is, ex. `build/tests/unit/framework/src/framework_ut`. Note: if you don't run ctest as a user that has write/read privileges to the `/var` or `/etc` directories, some tests may fail.

To see the code coverage report for a source file, cd to the directory where the object files are located, ex. `build/framework/CMakeFiles/svkframework.dir/src`. Make sure the `.gcda` and `.gcno` files are there and run `gcovr` (must be installed with pip), giving the source code dir and current working dir as parameters:

    cd build/framework/CMakeFiles/svkframework.dir/src
    gcovr -r {path_to_source_code} .

## SVK Application/Feature module integration
In order to install the necessary headers and libraries for feature modules to use, it is required to build Core module at the moment. In the future, we will have either a tar artifact or rpm to install.

Clone this repo and build core using the install prefix option, which you can use to install core to a given directory such as `/usr/local/svk/core`. Refer to the [Build & Installation](#build--installation) section above for how to install dependencies and build core. An example command for building and installing core:

    [root@msl-ssg-dev09 core]# sudo sh -c "./scripts/build.sh -r -p /usr/local/svk/core"
    [root@msl-ssg-dev09 core]#  ls /usr/local/svk/core/
    include  lib64  tests

This will install any headers and libs to `/usr/local/svk/core` for feature modules to use and link against.

### Using pkg-config to get flags needed for building with core
You can use the pkg-config file to get the necessary flags for building core.

Export the `PKG_CONFIG_PATH` variable with the location of the directory that contains `svkframework.pc` (should be your build directory by default) and run the `pkg-config` command. For example:

    export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/usr/local/svk/core/lib64/pkgconfig

    pkg-config --cflags svkframework
    -I/root/core/build/install_dir/include -DSPDLOG_COMPILED_LIB -DSPDLOG_FMT_EXTERNAL

    pkg-config --libs svkframework
    -L/root/core/build/install_dir/lib64 -lspdlog -pthread -lfmt

You can use the cmake pkgconfig to easily access the installed dirs in your cmake file:

    find_package(PkgConfig REQUIRED)
    pkg_check_modules(SVKFRAMEWORK REQUIRED svkframework)

    # Following vars are for getting libs/dirs
    ${SVKFRAMEWORK_INCLUDE_DIRS}
    ${SVKFRAMEWORK_CFLAGS_OTHER}
    ${SVKFRAMEWORK_LIBRARY_DIRS}
    ${SVKFRAMEWORK_LIBRARIES}

## Integration testing
For integration testing, you must build SVK Framework with the install prefix option as shown in the build script example above. This is needed to put the header files and libraries for SVK Management framework to consume. Once that is built and the `include` and `lib64` directories in the install dir are populated with the appropriate headers and libs, follow the instructions for SVK Management Framework build and give `include` directory as part of the build flag and the `lib64` directory as a node server startup option. For example:

    --framework_lib_path ../core/build/install_dir/lib64/

Then run the client command to the GRPC server to test end to end functionality. At least one feature module must be loaded for this to work.

To use the sample feature module, build SVK Framework with tests and list the `build/tests/sample_feature` directory in the core config. This will call the sample feature module functions and validate if the client can call the feature functions. The sample feature module has the same ID as power throttle (feature_id 0).

## Usage
Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.
