# SVK Application

## Description

🤡 A description of this project should be added here. 🤡

## Supported OS List

- Rockylinux 9
- Ubuntu 22.04

## Installation

The prefered method to install SVK Application is through your OS package manager.

SVK Application's CI/CD automatically produces release artifacts which are published to [SSG-Nexus](http://ssg-nexus.msl.lab:8081/), which you can browse from within the SSG lab network.

Release artifacts are also published to the [SVK Application Package Registry on Gitlab](https://cxl-gitlab.ssi.samsung.com/dfs/svk/sapp/-/packages).

Enable the SSG Nexus repo for your distro, then install the `svk-app` packages via the package manager:

### Ubuntu Installation

```bash
wget --quiet --output-document /usr/share/keyrings/ssg-nexus.pgp  http://ssg-nexus.msl.lab:8081/repository/svk_common/public.pgp
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ssg-nexus.pgp] http://ssg-nexus.msl.lab:8081/repository/svk_apt_ubuntu22 $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ssg-nexus.list
apt update
apt-get install svk-app -y

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

### Ubuntu Installation Instructions

Instructions are coming

## Usage

Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.

## Support

Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address, etc.

## Roadmap

If you have ideas for releases in the future, it is a good idea to list them in the README.

## Contributing

Thank you for your interest in contributing to SVK App

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

#### Bash code

- Use 4 spaces for indentation.

- Executable scripts should start with
  
  ```bash
  #!/usr/bin/env bash
  set -eu -o pipefail
  ```

- For the rest, follow
  [bahamas10's Bash Style Guide](https://github.com/bahamas10/bash-style-guide).

## Mysql

### Mysql Installation

1. Add the mysql repository in yum (process defined in: <https://dev.mysql.com/doc/mysql-yum-repo-quick-guide/en/>)
2. Enable/disable repos

   ```bash
   sudo yum-config-manager --disable mysql80-community
   sudo yum-config-manager --disable mysql-tools-community
   sudo yum-config-manager --enable mysql-innovation-community
   sudo yum-config-manager --enable mysql-tools-innovation-community
   ```

3. Install and run Mysql community server

   ```bash
   sudo yum install mysql-community-server
   systemctl start mysqld
   systemctl status mysqld
   sudo mysql_secure_installation
   ```

4. Change password for root mysql user

   ```bash
   mysql -u root -p
   ALTER USER 'root'@'localhost' IDENTIFIED BY 'my-password';
   ```

   You can retrieve temporary password with

   ```bash
   sudo grep 'temporary password' /var/log/mysqld.log
   ```

5. Setup mysql and create a user & create scfm database, execute the following commands and use the below credentials

   ```txt
   User: dev
   Pass: CXL123mem!
   ```

   ```bash
   mysql -u root -p
   CREATE USER 'dev'@'localhost' IDENTIFIED BY 'my-password';
   GRANT ALL ON *.* To 'dev'@'localhost';
   ```

6. Setup DB with the following script

   ```bash
   python3 cognos/backend/db_setup.py
   ```

## Influx DB

### InfluxDB Installation

Use the following Influx documentation: <https://docs.influxdata.com/influxdb/v2/install/> for Step-1 and Step-2

1. For Red Hat/CentOS/Fedora x86-64 (x64, AMD64) systems

   ```bash
   curl -LO https://download.influxdata.com/influxdb/releases/influxdb2-2.7.6-1.x86_64.rpm
   sudo yum localinstall influxdb2-2.7.6-1.x86_64.rpm
   ```

2. sudo service influxdb start

3. Download influx CLI package

   ```bash
   wget https://download.influxdata.com/influxdb/releases/influxdb2-client-2.7.5-linux-amd64.tar.gz
   ```

4. Unpackage downloaded influx CLI binary

   ```bash
   tar xvzf ./influxdb2-client-2.7.5-linux-amd64.tar.gz
   ```

5. Place the unpackaged influx executable in your system $PATH

   ```bash
   sudo cp ./influx /usr/local/bin/
   ```

6. run influx setup (for future deployment purposes there is a way to setup asynchronously)
We are able to configure retention in hours, use 720 for a 30 day retention

7. create All Access API token

   ```bash
   influx auth create --all-access --host http://localhost:8086 --org Samsung
   ```

8. install influxDB Python Client, must install InfluxDB v2 compatible version, <https://github.com/influxdata/influxdb-client-python>

   ```bash
   pip install 'influxdb-client[ciso]'
   ```

## Cognos InfluxDB Schema

```txt
Bucket: <User/Tenant>
  Measurement: <metric/alert/heartbeat/etc>
    Fields: {<metric1_name>:<metric1_value>, <metric2_name>:<metric2_value>, ...}
    Tags: {
      source: <host/application server>,
      source_type: <cxl_device/host/memory_box/application>,
      description: <description>,
      category: <memory/cpu/bandwidth/etc>,
      application: <app-name>
    }
    Timestamp: <timestamp>
```

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

### Python code

- Use Python version 3.10

- [flake8](https://pypi.org/project/flake8/) linter check should pass.

- [mypy](https://mypy.readthedocs.io/en/stable/) type check should pass.
  Type annotations are optional.

- Executable scripts should start with
  
```python
#!/usr/bin/env python3
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

## License

For open source projects, say how it is licensed.

## Project status

If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
