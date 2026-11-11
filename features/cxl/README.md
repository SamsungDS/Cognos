# Cognos CXL Plugin

## Description
Cognos CXL plugin interfaces with connected CXL devices downstream through fabric management and Cognos GUI upstream. It defines interfaces to read and update the CXL device state using fabric management interface. 

## Supported Build and Runtime Platforms
- Rockylinux 9
- Ubuntu 22
- Ubuntu 24
- At least 4 CPU Cores with 8GB RAM.

## Build

cxl is built and tested with the rest of Cognos, from the repository root: see
[Build](../../README.md#build) (`./build.sh cxl`, and `./build.sh --test cxl` for its unit tests).

## Mock device configuration

Cognos CXL does not need the cxl_memory_box library. The sample CXL device configuration is kept in this repository as `config/input.json`. The unit tests use it, and the release and mock packages install it to `/usr/local/svk/feature_modules/cxl/config/input.json`.

## Contributing
Thank you for your interest in contributing to Cognos CXL

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

Cognos CXL uses style check tools for C++ code, shell and python scripts.
As a prerequisite, install the tools below.

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

   Signed-off-by: John Doe <john.doe@example.com>
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

7. Auto-restart for CMM-H driver service
a) What is the feature
It was observed that occasionally the CMMH driver reported unusually high value for
temperature recorded by sensors in CMMH drives.  Restarting the CMMH driver stops the
reporting of those unusually high temperature values for a certain amount time before
reporting those unusual values again. So, it was decided that we need to restart
the CMMH driver whenever we observe high temperature from CMMH sensors.

b) How to enable/disable it
We can control this auto-restart of CMMH driver using the boolean value mentioned
for the key "auto_restart_cmmh_driver" in /usr/local/svk/feature_modules/cxl/config/cxl.conf.
By default, the value for the above-mentioned key is "false". If it is set to "true", the
auto-start will occur if the temperature recorded by the sensor is outside of the
normal operation range of 0 degree C and 100 degree C (32 degree F and 212 degree F).
In order to stop the auto-restart of CMM driver using the associated CMMH driver
service, we need to change the value of key "auto_restart_cmmh_driver" to be "false".
If the value for "auto_restart_cmmh_driver" key is false, the auto-restart of CMMH
driver does not happen but the requests for "get_device_stats" or "get_device_info"
will return responses with temperature value as 0.

c) Details of CMMH driver auto-restart
Whenever the temperature recorded is ouside the acceptable operational range mentioned
above and the "auto_restart_cmmh_driver" is set to "true", the CMMH driver service
restarts the CMMH driver executable located at /usr/local/bin/cmmh_driver.  Now, as
part of the restart of the CMMH driver service it first stops the Cognos Node service
that stops the associated Node process on the host.
The Node process is due executable located at /usr/local/svk/mgmt-fw/bin/svkgrpcnode.
Once the Node process stops, the CMMH driver process is stopped as well. For details
about the details of the CMMH driver service and the Node service please consult the
service details at /usr/lib/systemd/system/cmmh_driver.service and
/usr/lib/systemd/system/cognos-node.service files. As per the the relationship mentioned
in those service files, subsequently the CMMH driver service starts the CMMH driver
process and once the successful start of CMMH driver process is confirmed it starts the
Cognos Node service that starts the Node process on the host.
So, every time the CMMH driver service is restarted, any pending SCMC request that has
reached the Node process or is in queue to be placed for service by Node process will
get timed out since Node process gets restarted as well.

8. CMM-MP adapter plugin (libmpctl)
a) What is the feature
CMM-MP (CXL Memory Module - Multi Pathing) devices are integrated through the
DevCMMMP adapter plugin (libcmmmp.so, src/cmmmp), which wraps the prebuilt
libmpctl v0.3 library in third_party/libmpctl. The plugin registers with the
DeviceManager under the name "cmmmp" and exposes three kinds of devices:
- POOL: the memory pool visible to this server,
- MPDEV: each local and remote MP device (FW / FPGA version, chip id, capacity,
  back-end Ethernet link state, FPGA temperature),
- MPN: each memory pool node, which can be attached to the host as a NUMA node
  or devdax device.
Device IDs use the layout [47:32] vendor 0x1E98 | [31:16] kind code (pool
0xFF00, MP device 0xFF01, MPN 0xFF02) | [15:0] index (MP device slot_id, MPN id).

b) Build and runtime requirements
libmpctl.a is built with GCC 13 against glibc 2.38+ and uses libcxl, libndctl and
libdaxctl (Ubuntu: libcxl-dev, libndctl-dev, libdaxctl-dev; Rocky / OL:
cxl-devel, ndctl-devel, daxctl-devel). CMake checks that libmpctl links on the
build host and skips the plugin with a warning otherwise (e.g. on Ubuntu 22.04
and Rocky 9). Pass -DWITH_CMMMP=OFF to disable it explicitly. The plugin is
installed next to libcmmh.so in the plugin_dir configured in cxl.conf.

c) How to configure it
The "cmmmp" section of /usr/local/svk/feature_modules/cxl/config/cxl.conf
controls the adapter:
- "enabled": register CMM-MP devices (default true),
- "auto_pool_setup": run host-initiated discovery and pool create during device
  discovery when the pool is not ready (default false, as this changes pool-wide
  state shared with other servers),
- "default_attach_mode": "numa" or "devdax", used when attach does not request a
  mode (default "numa"),
- "expose_remote_mpdevs": register remote MP devices for observability
  (default true),
- "fpga_temp_warn_C": FPGA temperature above which an MP device reports
  "Warning" (default 85).

## Authors and acknowledgment
* Sukesh Nagaraja
* Rajashekhar Payagond
* Mandar Sawant
* Samaresh Singh
## License
Cognos is licensed under the Apache License, Version 2.0: see [LICENSE](../../LICENSE).
