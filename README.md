# SVK Web



## Getting started

To make it easy for you to get started with GitLab, here's a list of recommended next steps.

Already a pro? Just edit this README.md and make it your own. Want to make it easy? [Use the template at the bottom](#editing-this-readme)!

## Add your files

- [ ] [Create](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#create-a-file) or [upload](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#upload-a-file) files
- [ ] [Add files using the command line](https://docs.gitlab.com/ee/gitlab-basics/add-file.html#add-a-file-using-the-command-line) or push an existing Git repository with the following command:

```
cd existing_repo
git remote add origin https://cxl-gitlab.ssi.samsung.com/svk/web.git
git branch -M main
git push -uf origin main
```

## Integrate with your tools

- [ ] [Set up project integrations](https://cxl-gitlab.ssi.samsung.com/svk/web/-/settings/integrations)

## Collaborate with your team

- [ ] [Invite team members and collaborators](https://docs.gitlab.com/ee/user/project/members/)
- [ ] [Create a new merge request](https://docs.gitlab.com/ee/user/project/merge_requests/creating_merge_requests.html)
- [ ] [Automatically close issues from merge requests](https://docs.gitlab.com/ee/user/project/issues/managing_issues.html#closing-issues-automatically)
- [ ] [Enable merge request approvals](https://docs.gitlab.com/ee/user/project/merge_requests/approvals/)
- [ ] [Automatically merge when pipeline succeeds](https://docs.gitlab.com/ee/user/project/merge_requests/merge_when_pipeline_succeeds.html)

## Test and Deploy

Use the built-in continuous integration in GitLab.

- [ ] [Get started with GitLab CI/CD](https://docs.gitlab.com/ee/ci/quick_start/index.html)
- [ ] [Analyze your code for known vulnerabilities with Static Application Security Testing(SAST)](https://docs.gitlab.com/ee/user/application_security/sast/)
- [ ] [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/ee/topics/autodevops/requirements.html)
- [ ] [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/ee/user/clusters/agent/)
- [ ] [Set up protected environments](https://docs.gitlab.com/ee/ci/environments/protected_environments.html)

***

# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thank you to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README
Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name
Choose a self-explaining name for your project.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Badges
On some READMEs, you may see small images that convey metadata, such as whether or not all the tests are passing for the project. You can use Shields to add some to your README. Many services also have instructions for adding a badge.

## Visuals
Depending on what you are making, it can be a good idea to include screenshots or even a video (you'll frequently see GIFs rather than actual videos). Tools like ttygif can help, but check out Asciinema for a more sophisticated method.

## Installation
Within a particular ecosystem, there may be a common way of installing things, such as using Yarn, NuGet, or Homebrew. However, consider the possibility that whoever is reading your README is a novice and would like more guidance. Listing specific steps helps remove ambiguity and gets people to using your project as quickly as possible. If it only runs in a specific context like a particular programming language version or operating system or has dependencies that have to be installed manually, also add a Requirements subsection.

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

### Coding Style Guidelines

* All error messages should go to stderr.

#### Bash code

* Use 4 spaces for indentation.

* Executable scripts should start with
  ```bash
  #!/usr/bin/env bash
  set -eu -o pipefail
  ```

* For the rest, follow
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

# Execute the tests

[root@muser selenium]# python3 test_runner.py

#### Python code

* Use Python version 3.10

* [flake8](https://pypi.org/project/flake8/) linter check should pass.

* [mypy](https://mypy.readthedocs.io/en/stable/) type check should pass.
  Type annotations are optional.

* Executable scripts should start with
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
* Nadim Sarras
* Mohan Patidar

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
