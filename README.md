# SVK Application

## Description

SVKAPP is the top-most layer enabling Samsung Cognos Management Console.

SVKAPP consists of the following services;

cognos-app: Responsible for backend support of the webapplication, communicating
            with SVK CXL Plugin, storing metadata and state information, supporting
            storage and usage of InfluxDB client

cognos-subscriber: Consumes metrics published from publisher and stores them into InfluxDB

cognos-exporter: Pushes metrics from InfluxDB to UI

cognos-ui: UI for Samsung Management Console

## Supported OS List

- Rockylinux 9
- Ubuntu 22.04

## Installation

The prefered method to install SVK Application is through your OS package manager.

SVK Application's CI/CD automatically produces release artifacts which are published to [SSG-Nexus](http://ssg-nexus.msl.lab:8081/), which you can browse from within the SSG lab network.

Release artifacts are also published to the [SVK Application Package Registry on Gitlab](https://cxl-gitlab.ssi.samsung.com/dfs/svk/sapp/-/packages).

Enable the SSG Nexus repo for your distro, then install the `svk-app` packages via the package manager:

### Ubuntu Installation

Dependencies;
 - python3.10
 - python3-pip
 - python3.10-venv
 - nodejs
 - npm

Installation Instructions for svk-app debian package
```bash
wget --quiet --output-document /usr/share/keyrings/ssg-nexus.pgp  http://ssg-nexus.msl.lab:8081/repository/svk_common/public.pgp
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ssg-nexus.pgp] http://ssg-nexus.msl.lab:8081/repository/svk_apt_ubuntu22 $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ssg-nexus.list
apt update
apt-get install svk-app -y

```

Post Installtion Steps;
1. Install MySQL

```sudo apt install mysql-server```
```sudo mysql_secure_installation```

login with root user to Mysql console
```sudo mysql -u root```

Create Dev User
```
CREATE USER 'dev'@'localhost' IDENTIFIED BY 'my-password';
GRANT ALL ON *.* To 'dev'@'localhost';
```
Run DB setup script
```
/usr/local/svk/svk-app/env/bin/python3 /usr/local/svk/svk-app/cognos/backend/db_setup.py
```

2. Install InfluxDB
```sudo apt update```
Import repository key
```
curl -fsSL https://repos.influxdata.com/influxdata-archive_compat.key|sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/influxdata.gpg
```
Add InfluxDB APT repository
```
echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdata.gpg] https://repos.influxdata.com/debian stable main' | sudo tee /etc/apt/sources.list.d/influxdata.list
```
Update apt index and install InfluxDB
```
sudo apt install influxdb2
```
Use the InfluxDB UI to configure and setup the user/org/token/etc..
navigate to http://<ip>:8086/ and follow the steps


3. Configure the following configuration files appropiately
```
/usr/local/svk/svk-app/cognos/backend/config/config.json
/usr/local/svk/svk-app/cognos/backend/config/influxdb_config.json
/usr/local/svk/svk-app/cognos/exporter/config/config.json
/usr/local/svk/svk-app/cognos/ui/src/config/config.json
/usr/local/svk/svk-app/cognos/cognos.config
```
4. Run the services
```
sudo systemctl start cognos-subscriber
sudo systemctl start cognos-exporter
sudo systemctl start cognos-app
sudo systemctl start cognos-ui
```

5. You can perform smoke testing by the following 
navigate to /usr/local/svk/svk-app/cognos/health/test folder
```
chmod +x ./smoke_test.sh
./smoke_test.sh 
```

### Rockylinux Installation

```bash
curl -fsSL http://ssg-nexus.msl.lab:8081/repository/svk_common/ssg-nexus-$(. /etc/os-release && echo "$ID${VERSION_ID%%.*}").repo -o /etc/yum.repos.d/ssg-nexus.repo
dnf install epel-release -y
dnf install svk-app -y
```

## Release build

To create a release build, execute the `scripts/build.sh` script with the `--release` or `-r` flag:

```bash
./scripts/build.sh -r
```

This will produce either an RPM or Debian package, depending on whether the build is performed on a Rocky or Ubuntu OS repsectively.

Release artifacts can be found in the `./build/artifacts` directory after executing the build script.

## Developer installation

Installing SVK APP dependencies can simply be done by running the following command from the sapp directory

```bash
./scripts/dependencies/install.sh
```

1. Install Mysql, [follow instructions in Mysql section of README](#mysql)
2. Install reactjs and required  packages with npm:

   ```bash
   cd cognos/backend/ui
   npm install
   ```

3. Ensure the following config files are properly set:

   ```txt
   cognos/backend/config/config.json
   cognos/backend/config/influxdb_config.json
   cognos/ui/config/config.json
   cognos/exporter/config/config.json
   ```

4. Run CAL layer with:

   ```bash
   cd cognos/backend
   python3 -m flask run -h <localip> -p 4000 --mock
   ```

5. Run Exporter:

   ```bash
   cd cognos
   python3 exporter/exporter.py --mock
   ```

6. Run Subscriber:

   ```bash
   cd cognos
   python3 subscriber/sub_client.py subscriber/mock_publisher_events.output
   ```

7. Run UI:

   ```bash
   cd cognos/ui
   npm start
   ```

## Usage

### Operational Modes
Samsung Cognos Management Console can operate in 3 modes

1. Mock mode: In order to enable faster development / prototyping, as well as quick validation of
   the UI, Cognos is able to run in mock mode. Mock mode means that no hardware and no other
   components below the SVKAPP layer will be used. In order to configure "Mock Mode" ensure that 
   the cognos.config MODE variable is set to "mock".

2. Simulated Mode: Simulated mode is still technically a "mock mode", however it entails running
   the entire SVK stack. Specfically these components include UI, exporter, subscriber, app, 
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
sudo systemctl start cognos-app
sudo systemctl start cognos-exporter
sudo systemctl start cognos-ui
```

### Requesting changes

To request changes,
[log an issue](https://cxl-gitlab.ssi.samsung.com/dfs/svk/sapp/-/issues/new)
and describe the problem you are facing.

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

- All error messages should go to stderr.

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

## Python Selenium Test Cases for Cognos UI

Enabled Selenium Test Enivornment to test Cognos web application.

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

   Signed-off-by: John Doe <john.doe@samsung.com>
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

Alpha.0 release complete

Supported SVKAPP Features:
- Metrics data consumption and visualization
- Immutable and Mutable operations through UI
- Samsung Management Console UI
