# SVK Core

## Description

SVK Core contains utilities and framework for [Management Framework](../mgmt-fw/README.md) as well as other Cognos components to communicate with feature modules such as power throttling, etc. See [SVK Application/Feature module integration](#svk-applicationfeature-module-integration) for details related to integrating feature modules with SVK Core.

### Supported OS List

- Rockylinux 9
- Ubuntu 22.04
- Ubuntu 24.04
- Oracle Linux 10

## Build

core is built and tested with the rest of Cognos, from the repository root: see
[Build](../../README.md#build) (`./build.sh core`, and `./build.sh --test core` for its unit tests).

## SVK Application/Feature module integration

Install the `cognos-core` and `cognos-core-dev` packages (see [Build](#build)) to get the headers and libraries for feature modules to use.

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
