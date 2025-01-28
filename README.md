# SVK CXL Plugin

## Description
SVK CXL plugin interfaces with connected CXL devices downstream through fabric management and Cognos GUI upstream. It defines interfaces to read and update the CXL device state using fabric management interface. 
For more details, see http://sj-confluence.ssi.samsung.com:8090/display/MPL/High+Level+Design+of+Samsung+Cognos+Management+Console.

## Supported Build and Runtime Platforms
- Rockylinux 9
- Ubuntu 22
- At least 4 CPU Cores with 8GB RAM.

## Install build dependencies
```bash
./scripts/dependencies/install.sh
```

### SVK Dependencies

The [dependencies install script](#Install-build-dependencies) will configure your build environment to pull packages from [SSG Nexus](http://ssg-nexus.msl.lab:8081).

The following SVK dependencies are installed automatically by the above script, but can be manually updated, if necessary, using your OS's package manager:

- `svk-core`
- `svk-core-dev` (Ubuntu) or `svk-core-devel` (Rockylinux)
- `svk-grpc`
- `svk-go-modules`
- `svk-mgmt-fw`

### Manual upgrade of SVK Packages

#### Rockylinux

```bash
dnf clean all
dnf config-manager --add-repo=http://ssg-nexus.msl.lab:8081/repository/svk_yum_rocky9/
dnf install svk-core-devel svk-grpc svk-go-modules  -y
dnf install svk-mgmt-fw

# Optional - install devel package
dnf install svk-mgmt-fw-devel -y
```

#### Ubuntu

```bash
wget --quiet --output-document /usr/share/keyrings/ssg-nexus.pgp  http://ssg-nexus.msl.lab:8081/repository/svk_common/public.pgp
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ssg-nexus.pgp] http://ssg-nexus.msl.lab:8081/repository/svk_apt_ubuntu22 $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ssg-nexus.list
apt-get update
apt-get install svk-core-dev svk-grpc svk-go-modules -y
apt-get install svk-mgmt-fw -y
# Optional - install devel package
apt-get install svk-mgmt-fw-dev -y
```

### Get the Sources

#### SVK CXL

git clone --recursive https://cxl-gitlab.ssi.samsung.com/dfs/svk/cxl.git

#### CXL Mem box API (cxl_memory_box)
CXL Mem box API implements a low level cxl fabric management API for Samsung CXL memory box. SVK CXL plugin uses the same to execute immutable and mutable functions on Samsung CXL memory box, e.g. attach/detach CXL memory device to and from an application server.

For more details, please see http://sj-confluence.ssi.samsung.com:8090/display/MPL/CXL+memory+box+FM+APIs.

git clone --recursive https://cxl-gitlab.ssi.samsung.com/cxl/cxl_memory_box.git

##### Requesting access and more information

Assuming you already have access to https://cxl-gitlab.ssi.samsung.com/, if not please contact Samsung IT.
For additional access permissions and information on https://cxl-gitlab.ssi.samsung.com/cxl/cxl_memory_box.git please contact mukesh.garg@samsung.com (owner/maintainer) or changho.c@samsung.com.

#### Build with CXL Memory box API

https://cxl-gitlab.ssi.samsung.com/cxl/cxl_memory_box/-/blob/main/mbox_a1/README.md

##### Two modes for CXL Memory box build

- Simulated Mode 
```bash
git clone git@cxl-gitlab.ssi.samsung.com:cxl/cxl_memory_box.git  
cd mbox_a1  
mkdir build  
cd build  
cmake -DCMAKE_CXX_FLAGS="-DENABLE_SIM" ..
make  
```

- Hardware Mode
```bash
git clone git@cxl-gitlab.ssi.samsung.com:cxl/cxl_memory_box.git  
cd mbox_a1  
mkdir build  
cd build  
cmake.. && make  
```


#### Link FM API with SVK CXL

For example,
```
[mandar.s@msl-ssg-vm11 cxl]$ scripts/build.sh --with-fmapi /home/mandar.s/cxl/svk-cxl/cxl_memory_box/mbox_a1/build/libmbox_a1_shared.so /home/mandar.s/cxl/svk-cxl/cxl_memory_box/mbox_a1/ --mock
Build tests: false
Build with code coverage: false
CMake install prefix:
~/cxl/svk-cxl/cxl/build ~/cxl/svk-cxl/cxl
Cmake options: -DWITH_FMAPI=ON
Cmake options: -DCMAKE_INCLUDE_PATH=/home/mandar.s/cxl/svk-cxl/cxl_memory_box/mbox_a1/
Cmake options: -DCMAKE_LIBRARY_PATH=/home/mandar.s/cxl/svk-cxl/cxl_memory_box/mbox_a1/build/libmbox_a1_shared.so
Running cmake...
-- GIT VERSION 0.0.0
-- GIT VERSION strip 0.0.0
-- Building with coverage
-- Building with FMAPI
-- Configuring done (0.6s)
-- Generating done (0.5s)
-- Build files have been written to: /home/mandar.s/cxl/svk-cxl/cxl/build
Building libraries...
make...
[ 14%] Built target cxl_lib
[ 28%] Built target gtest
[ 42%] Built target gtest_main
[ 57%] Built target gmock
[ 71%] Built target gmock_main
[100%] Built target cxl_ut
~/cxl/svk-cxl/cxl
```

## Building and executing unit tests

- Execute `./scripts/build.sh` script from the top level directory. The `-h` option will show what options are available for building SVK CXL Plugin:

```bash
./scripts/build.sh -h
Build script for SVK CXL Plugin

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
--with-fmapi <FMAPI_LIB_PATH> <FMAPI_INCLUDE_PATH>
  Builds with fmapi. Requires fmapi library and source paths.
e.g. scripts/build.sh --with-fmapi /cxl_memory_box/mbox_a1/build/libmbox_a1_shared.so /cxl_memory_box/mbox_a1
```

### Unit Tests and Code Coverage

Execute the following script to build with unit tests, and display code coverage results:

```bash
#mock mode:
./scripts/build.sh --mock -t -c

#hardware mode
./scripts/build.sh -t -c

e.g. output

[100%] Built target cxl_ut
~/cxl/svk-cxl/cxl/build/tests ~/cxl/svk-cxl/cxl/build ~/cxl/svk-cxl/cxl
Running unit tests...
Test project /home/mandar.s/cxl/svk-cxl/cxl/build/tests
      Start  1: ScHostTest.ParameterizedConstructor
 1/19 Test  #1: ScHostTest.ParameterizedConstructor ............   Passed    0.07 sec
      Start  2: ScHostTest.GetCompositeObj
 2/19 Test  #2: ScHostTest.GetCompositeObj .....................   Passed    0.08 sec
      Start  3: ScHostTest.EmptyHostNameTest
 3/19 Test  #3: ScHostTest.EmptyHostNameTest ...................   Passed    0.18 sec
      Start  4: ScHostTest.ValidHostNameAndPort
 4/19 Test  #4: ScHostTest.ValidHostNameAndPort ................   Passed    0.15 sec
      Start  5: ScHostTest.ValidScId
 5/19 Test  #5: ScHostTest.ValidScId ...........................   Passed    0.13 sec
      Start  6: ScHostTest.ValidDeviceName
 6/19 Test  #6: ScHostTest.ValidDeviceName .....................   Passed    0.14 sec
      Start  7: ScHostTest.InvalidHostNameException
 7/19 Test  #7: ScHostTest.InvalidHostNameException ............   Passed    0.06 sec
      Start  8: ScHostTest.InvalidPortValue
 8/19 Test  #8: ScHostTest.InvalidPortValue ....................   Passed    0.07 sec
      Start  9: ScHostTest.ZeroCapacity
 9/19 Test  #9: ScHostTest.ZeroCapacity ........................   Passed    0.06 sec
      Start 10: ScHostTest.ValidCapacity
10/19 Test #10: ScHostTest.ValidCapacity .......................   Passed    0.07 sec
      Start 11: ScHostTest.OverCapacity
11/19 Test #11: ScHostTest.OverCapacity ........................   Passed    0.05 sec
      Start 12: ScHostTest.TargetPorts
12/19 Test #12: ScHostTest.TargetPorts .........................   Passed    0.06 sec
      Start 13: ScIdTest.ParameterizedConstructor
13/19 Test #13: ScIdTest.ParameterizedConstructor ..............   Passed    0.05 sec
      Start 14: ScIdTest.ParameterizedConstructor_LargeValue
14/19 Test #14: ScIdTest.ParameterizedConstructor_LargeValue ...   Passed    0.06 sec
      Start 15: ScIdTest.GetScId
15/19 Test #15: ScIdTest.GetScId ...............................   Passed    0.05 sec
      Start 16: ScIdTest.SetScId
16/19 Test #16: ScIdTest.SetScId ...............................   Passed    0.05 sec
      Start 17: ScIdTest.SetScId_NegativeValue
17/19 Test #17: ScIdTest.SetScId_NegativeValue .................   Passed    0.05 sec
      Start 18: ScIdTest.HashScId
18/19 Test #18: ScIdTest.HashScId ..............................   Passed    0.05 sec
      Start 19: ScIdTest.HashScId_DistinctObjectsSameValue
19/19 Test #19: ScIdTest.HashScId_DistinctObjectsSameValue .....   Passed    0.06 sec

100% tests passed, 0 tests failed out of 19

Total Test time (real) =   1.57 sec
~/cxl/svk-cxl/cxl/build ~/cxl/svk-cxl/cxl
Generating coverage reports
```

#### Build without CXL Memory box API

cd cxl && scripts/build.sh


#### Build RPMS
e.g.
cd cxl && scripts/build.sh --with-fmapi mbox_a1/build/libmbox_a1_shared.so mbox_a1 -r -b


#### Build Debian pacakages
e.g.
cd cxl && scripts/build.sh --with-fmapi mbox_a1/build/libmbox_a1_shared.so mbox_a1 -r -b

Note: for mock binary use "--mock" flag


## Contributing
Thank you for your interest in contributing to SVK CXL

### Sending patches

0. [Fork](https://guides.github.com/activities/forking/) the repository
   (once).

1. Create a new branch.
   E.g.,
   ```
   git checkout -b save-the-prince
   ```

2. Implement the change, adhering to the [Coding Style Guidelines](#Coding Style Guidelines)

3. Prepare a commit in accordance with [Patch Requirements](#Patch Requirements)

   **Note:** use `git commit --signoff` to commit your code changes.
   You can enable `--signoff` by default with
   ```
   git config --local --add format.signOff true
   ```

### Coding Style Guidelines

SVK CXL uses style check tools for C++ code, shell and python scripts.
As a prerequisite, install the tools with specific versions mentioned at http://sj-confluence.ssi.samsung.com:8090/pages/viewpage.action?pageId=322801744#SVKCodingStandards&Styles-Consensus to be in sync with the gitlab pipelines.

#### Running shellcheck


```
shellcheck --version
ShellCheck - shell script analysis tool
version: 0.9.0
license: GNU General Public License, version 3
website: https://www.shellcheck.net
$ cat > checkstyle2junit.xslt <<EOL # collapsed multi-line command
$ git ls-files --exclude='*.sh' --ignored -c -z | xargs -t --no-run-if-empty -0 shellcheck --format=checkstyle | xmlstarlet tr checkstyle2junit.xslt > shellcheck.xml
shellcheck --format=checkstyle scripts/build.sh scripts/dependencies/install.sh scripts/dependencies/os/common.sh scripts/dependencies/os/rocky.sh scripts/run-tests.sh
```

#### Running clang-format

```
clang-format -i --style=file src/*.cc src/*.h
```

#### Running pycodestyle check

```
pycodestyle ./ --show-source --show-pep8
```

### Patch Requirements
1. Maintainers, Contributors and Reviewers MUST have a Platform account
   and SHOULD use their real names or a well-known alias.

2. A patch SHOULD be a minimal and accurate answer to exactly one
   identified and agreed problem.

3. A patch MUST adhere to the code style guidelines of the project if
   these are defined.

4. A patch MUST compile cleanly and pass project self-tests on at least
   the principal target platform.

5. A patch commit message SHOULD consist of a single short (less than
   50 characters) line stating the problem ("<module/dir>: ...") being
   solved, followed by a blank line and then a brief description of the problem followed by the solution
   and corresponding merge request link for additional details as described below.
   ```
   Header line <typically dir/module name having changes>: explain the commit in one line (use the imperative)
   Body of commit message is a few lines of text, explaining things
   in more detail, possibly giving some background about the issue
   being fixed, etc etc.

   The body of the commit message can be several paragraphs, and
   please do proper word-wrap and keep columns shorter than about
   74 characters or so. That way "git log" will show things
   nicely even when it's indented.

   Make sure you explain your solution and why you're doing what you're
   doing, as opposed to describing what you're doing. Reviewers and your
   future self can read the patch, but might not understand why a
   particular solution was implemented.
   ```
   Example of a good commit message,
   ```
   baz: fix foo() to enable bar()

   bar() is never visited because condition xyz in foo() is invalid and
   is never true.

   - Fix condition xyz to abc to enable bar()'s visit from foo().
   - Fix test ut::foo() to validate bar()'s visit.

   MR: !123

   Signed-off-by: John Doe <john.doe@samsung.com>
   ```
<!--
  -- The strictness of the `Problem: ` prefix requirement is controversial[1].
  -- ZeroMQ maintainers considered the proposal of reducing the strictness
  -- (s/MUST/SHOULD/), but decided against[2] it, stating that current style
  -- is foundational[3].
  --
  --   1. https://github.com/zeromq/rfc/issues/117
  --   2. https://github.com/zeromq/rfc/issues/117#issuecomment-249374914
  --   3. https://github.com/zeromq/rfc/issues/117#issuecomment-249391434
  --
  -- | The `Problem` statement wields enormous power. At first you need to
  -- | recognize that every bug, every feature, every change and every idea is
  -- | essentially a problem. Thus having a list of solved problems comes
  -- | naturally. Using the `Problem` statement also sharpens the awareness
  -- | whether a feature, bug, change or idea is actually worth solving as it
  -- | is really easy to see if there is a need. Further it forces developers
  -- | to consciously fragment their work into a stream of small fixes rather
  -- | than one big with a <censored>nonsensical</censored> commit message or
  -- | even a listing.
  -- |
  -- | From a maintainers perspective it allows us to quickly examine a pull
  -- | request and merge it in a manner of seconds or decline it if the
  -- | problem statement is false. And probably most important it is a
  -- | powerful tool to identify bad actors as they wont follow rules.
  -->

6. A "Correct Patch" is one that satisfies the above requirements.

## Authors and acknowledgment
* Sukesh Nagaraja
* Rajashekhar Payagond
* Mandar Sawant

## License
For open source projects, say how it is licensed.
