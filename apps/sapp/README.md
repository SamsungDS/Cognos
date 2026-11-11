# SVK Application

## Description

SVKAPP is the top-most layer enabling Samsung Cognos Management Console.

SVKAPP consists of the following services;

cognos-app: Responsible for backend support of the webapplication, communicating
            with SVK CXL Plugin, storing metadata and state information, supporting
            storage and usage of InfluxDB client, transferring Cognos Events to UI.

cognos-subscriber: Consumes metrics published from publisher and stores them into InfluxDB

caddy: service that runs compiled UI for Samsung Management Console

## Supported OS List

- Ubuntu 22.04
- Oracle linux 10
- Oracle linux 9

## Versioning

The version of svk-app is retrievable from the generated VERSION file
during the packaging process or by manually running the following;
```./scripts/get_version.sh > ./VERSION```

The VERSION file will automatically be placed in the root of the package
install location or in the root of the repository when running in dev mode.

Versioning follows the following schema
```svk-app.<major_verison>.<minor_version>.<patch_version>```

## Build

sapp is built and tested with the rest of Cognos, from the repository root: see
[Build](../../README.md#build) (`./build.sh sapp`, and `./build.sh --test sapp` for its unit tests).

## SSL Configuration
SSL mode must be configured in cognos-app. This will enable https REST requests
to reach cognos-app. 

in the following config file set the following parameters to your cert and key file and set "ssl" to true

cognos/backend/config/config.json
```
"ssl_cert": "<path to ssl cert file>",
"ssl_key": "<path to ssl key file",
"ssl": false
```

## Usage

### Operating Assumptions
The following assumptions are made regarding SCMC usage and the underlying Cognos System
- every node_name is unique
- device name is derived from the device type and the last 5 digits of the device id
- FM_id and FM_endpoint requests args to CXL are dummy values

### Operational Modes
Samsung Cognos Management Console can operate in 3 modes

1. Mock mode: In order to enable faster development / prototyping, as well as quick validation of
   the UI, Cognos is able to run in mock mode. Mock mode means that no hardware and no other
   components below the SVKAPP layer will be used. In order to configure "Mock Mode" ensure that 
   the cognos.config MODE variable is set to "mock".

2. Simulated Mode: Simulated mode is still technically a "mock mode", however it entails running
   the entire SVK stack. Specfically these components include UI, subscriber, app, 
   SVK node server, SVK restserver, and SVK controller server. In order to run in this mode set
   cognos.config MODE to "real" and ensure the installed SVK CXL artifiact is the "sim" version. 

3. CXL Mode: This is the main intended use of Cognos. This mode enables Cognos to interact with
   and monitor real hardware. To use this mode set cognos.config MODE to "real" and ensure that
   you are using the CXL version of the SVK CXL Plugin artifact upon installation.

### Order of service-based execution for Cognos Full Stack upon production installation
```
sudo systemctl start svk-controller
sudo systemctl start svk-node
sudo systemctl start svk-restserver
sudo /usr/local/svk/mgmt-fw/bin/svksvcmgr --svk_conf_file /etc/svk/mgmt_fw_config.json &
sudo systemctl start cognos-subscriber
telegraf --config /usr/local/svk/svk-app/cognos/telegraf/telegraf.conf
sudo systemctl start cognos-app
sudo systemctl start cognos-rbac
sudo systemctl restart caddy
```

### Requesting changes

To request changes, log an issue in this repository and describe the problem you are facing.

### Sending patches

0. [Fork](https://guides.github.com/activities/forking/) the repository
   (once).

1. Create a new branch.
   E.g.,

   ```sh
   git checkout -b save-the-prince
   ```

2. Implement the change, adhering to the [Coding Style Guidelines](#Coding Style Guidelines)

3. Prepare a commit in accordance with [Patch Requirements](#Patch Requirements)

   **Note:** use `git commit --signoff` to commit your code changes.
   You can enable `--signoff` by default with

   ```sh
   git config --local --add format.signOff true
   ```

### Coding Style Guidelines

- ALL functions should contain a docstring indicating the inputs and return of that function
- ALL functions should have the input parameters and the return type hinted
- Simplicity and clean code is greatly valued over complex functions that do more

### Python code

- Use Python version 3.10

- [flake8](https://pypi.org/project/flake8/) linter check should pass.

- [mypy](https://mypy.readthedocs.io/en/stable/) type check should pass.
  Type annotations are optional.

- Executable scripts should start with
  
```python
#!/usr/bin/env python3
```

#### Bash code

- Use 4 spaces for indentation.

- Executable scripts should start with
  
  ```bash
  #!/usr/bin/env bash
  set -eu -o pipefail
  ```

- For the rest, follow
  [bahamas10's Bash Style Guide](https://github.com/bahamas10/bash-style-guide).

## Unit Tests

### Backend Unit Tests

This repo leverages the Pytest framework to test for backend code including cognos-app. Subscriber
module leverages the traditional unit test model in python. 

In order to run unit tests simply go to the source code directory of that module, i.e. cognos/backend and run;

```
python3.10 -m pytest -s --cov .
```

You will then see a report generated of which test cases passed along with a summary of code coverage for the
underlying source code. 

To execute pytest for a single file or even a specfic test case, run as so;

```
python3 -m pytest test/<test file>::<test case> -s -vvvvv --tb=long
```

### Frontend Unit Tests

We leverage Jest, a Node-based runner to execute unit tests for the UI code. All UI test cases are defined in the
following directory;
```
cognos/ui/src/tests/
```

*All tests should be exexcuted from the cognos/ui/src/ directory.

To execute frontend tests and generate a code coverage report simply run
```
npm run test:coverage
```

To execute frontend unit tests for a specific file you can use the command below. Jest will automatically find any
matching file names in subdirectories
```
npm test -- <filename>
```

### Unit Test Code Quality
The repo contains a policy to ensure that all source code maintains at least 70% code coverage and that all new code
checked in also maintains a 70% code coverage threshold.

## Integration Tests

In order to validate the front-facing functionality and integration amongst Cognos components, the integration
tests consist of a suite of test cases written in Selenium to test the Cognos web application. These integrations tests
run in the Git pipeline whenever new code is merged to ensure that all of the components integrate and produce the 
desired top level functionality. 

*Future Plan: Build integration tests across layers of stack and not just at the top level. 

Currently, integration tests only asses the top-level functionality, meaning the integration tests sit on top of the UI layer.
Therefore, the source code for the integration tests can be found in the following directory;
```
cognos/ui/tests/it/selenium/
```

Below are the instructions to run the integration tests.

### Prerequisites

Before running the python selenium tests, make sure you have to install the following.

1. Install Python3.10 or above
2. python3 -m pip install selenium
3. Install google chrome [Latest Version]

Refer "requirements.txt" file to install the dependencie ssoftwares to run the code.

### Process to run python selenium tests

To run the python selenium tests, follow these steps

1. Clone the directory containing python selenium test files to your local machine
2. Install the required prerequisites.
3. Configure Appication url, pages url as per configure file
4. Check the mandatory inputs required to run the test files.

## Execute the tests

[root@muser selenium]# python3 test_runner.py

## Patch Requirements

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

   ```txt
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

   ```txt
   baz: fix foo() to enable bar()

   bar() is never visited because condition xyz in foo() is invalid and
   is never true.

   - Fix condition xyz to abc to enable bar()'s visit from foo().
   - Fix test ut::foo() to validate bar()'s visit.

   MR: !123

   Signed-off-by: John Doe <john.doe@example.com>
   ```

   ```txt
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
   ```

6. A "Correct Patch" is one that satisfies the above requirements.

## Authors and acknowledgment

- Nadim Sarras
- Mohan Patidar

## Project status

MVP.1 release complete

Supported SVKAPP Features:
- Metrics data consumption and visualization
- Immutable and Mutable operations through UI
- Samsung Management Console UI
