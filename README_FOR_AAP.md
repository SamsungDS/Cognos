# Cognos Ansible README For Ansible Automation Platform (AAP)

## Preconditions

Cognos artifacts, cognos ansible playbooks and Ansible Automation Platform are ready.

### Local Project deployment on AAP

1. Login to AAP installed host, and then copy **cognos ansible playbooks** to `/var/lib/awx/projects` directory.
2. Login to AAP system, and then **create a project**.

   **Project Description:**

    A project is a logical collection of Ansible playbooks, represented in automation controller.

    For a local project, manually place the playbooks in the `Project Base Path` on your automation controller server.

    **Created Steps:**
    * From the navigation panel, select **Resources → Projects**.
    * On the **Projects** page, click **Add** to launch the **Create Project** window.
    * Enter the appropriate details into the following required fields:
        * **Name** (required)
        * Optional: **Description**
        * **Organization** (required): A project must have at least one organization.
        * Optional: **Execution Environment**: Enter the name of the execution environment or search from a list of existing ones to run this project.
        * **Source Control Type** (required): Select an SCM type as `Manual`.
        * **Project Base Path**: Default is `/var/lib/awx/projects` and cannot be changed.
        * **Playbook Directory**: The root directory name for Cognos Ansible playbooks.
    * Click **Save**.

3. Configure your inventories

    Red Hat Ansible Automation Platform works against a list of managed nodes or hosts in your infrastructure that are logically organized, using an inventory file. You can use the Red Hat Ansible Automation Platform installer inventory file to specify your installation scenario and describe host deployments to Ansible.

    By using an inventory file, Ansible can manage a large number of hosts with a single command. Inventories also help you use Ansible more efficiently by reducing the number of command line options you have to specify.

    Inventories are divided into groups and these groups contain the hosts.

    **Create an inventory**
    * From the **navigation** panel, select **Resources → Inventories**. The Inventories window displays a list of the inventories that are currently available.
    * Click **Add**, and select `Add inventory` to create.
    * Enter an `inventory` name and choose an `organization`, and then click **Save**.

    * Adding **permissions** to inventories
        * From the navigation panel, select **Resources → Inventories**.
        * Select the inventory name, and in the **Access** tab, click **Add**.
        * Select **a user** or **team** to add and click **Next**.
        * Select the **check box** next to a name to add one or more users or teams from the list as members.
        * Click **Next**.
        * Select the **roles** you want the selected users or teams to have. Scroll down for a complete list of roles. Different resources have different options available.
        * Click **Save** to apply the roles to the selected users or teams and to add them as members.

    * Adding **groups** to inventories

        **Adding `management_server` group**
        * Click the **inventory name**, and in the **Groups** tab, click **Add**.
        * Enter the appropriate details:
            * Enter the `management_server` in **Name** field.
            * Optional: **Description**: Enter a description as appropriate.
            * **Variables**: Enter definitions and values to be applied to all hosts in this group. Enter variables using either JSON or YAML syntax.

            Examples for YAML syntax.

                        ---
                        cognos_pkg_dir: "{{ inventory_dir }}/artifacts/SVK"
            * Click **Save**.

        **Adding `application_server` group**
        * Click **Back to Groups** tab, and then click **Add**.
        * Enter the appropriate details:
            * Enter the `application_server` in **Name** field.
            * Optional: **Description**: Enter a description as appropriate.
            * **Variables**: Enter definitions and values to be applied to all hosts in this group. Enter variables using either JSON or YAML syntax.

            Examples for YAML syntax.

                    ---
                    cognos_pkg_dir: "{{ inventory_dir }}/artifacts/SVK"
            * Click **Save**.

    * Adding **hosts** to an inventory

        * Click **the Inventory name** you want to add hosts to.
        * In the Inventory **Details** page, select the **Hosts** tab.
        * Click **Add**.
        * Enter `hostname` to create a new host.
        * Click **Save**
        * Ensure the toggle to **On** to include this host while running jobs.
        * Click **Group** tab, click **Add** and then select one of groups name of `application_server` and `management_server`.
        * Click **Save**.
        * Click **Back to Hosts**, and repeat the adding hosts steps to add more hosts and bound it to groups.

4. Create an credential

    * From the navigation panel, select **Resources → Credentials**.
    * Click **Add** to open **Create New Credential** page.
    * Enter a name in the **Name** field
    * Select the **Credential Type** as `Machine`.
    * Provide the **Username** and **Password** using the ansible deployment account details.
    * Click **Save** to successfully create the credential.

5. Create job templates

    A job template is a definition and set of parameters for running an Ansible job. Job templates are useful to run the same job many times.

    **Procedure of creating a job template**

    * On the **Templates** list view, select **Add job template** from the **Add** list.

    * Enter the appropriate details in the following fields
        * **Name**: Enter a name for the job.
        * **Job Type**: Select `Run`.
        * **Inventory**: Choose the inventory which is created in **step3**.
        * **Project**: Choose the project which is created in **step2**.
        * **Execution Environment**: Select `Default execution environment`.
        * **Playbook**: Choose the Choose the playbook to be launched with this job template from the available playbooks.
            * **For deploy cognos**: select or enter `playbooks/deploy_cognos.yml` from the drop-down list.
            * **For cleanup cognos**: select or enter `playbooks/remove_cognos.yml` from the drop-down list.
        * **Credentials**: Select the credential name which is created in **step4**.

    * **Variables**: copy the content from `group_vars/all/all.yml` to this field with 'YAML' format.

        * The following variables can be changed according your deployment requirements.
            * `influxdb_uninstall_flag: false`: the default is `false`. Change to `true` if you want remove influxdb and it's data when cleanup cognos deployment.
            * `cognos_install_gui_enabled: false`: the default is `false`. Change to `true` if you want deploy SCMC as part of deploy cognos.
            * `cognos_rbac_enabled: true`: the default is `true`. The variable only works in condition of `cognos_install_gui_enabled: true`, `true` means deploy SCMC with RBAC service enabled. If change this value to `false`, the SCMC would be deployed without RBAC.
            * `cognos_certificates_enabled: false`: the default is `false`. `false` means cognos related APIs are work in **http** mode. `true` means cognos Rest APIs are work in both **https** and **http** mode, the SCMC works in **https** mode.
            * `cognos_cleanup_enable_log_collection: false`:  The default is `false`. `false` means to skip log collection when running the remove_cognos.yml playbook. Change to `true` means collect logs at the start of running the remove_cognos.yml playbook.

    * Click **Save**.

6. Configure job settings

    Automation controller’s use of automation execution environments and Linux containers prevents playbooks from reading files outside of their project directory.

    By default, the only data exposed to the ansible-playbook process inside the container is the current project being used.

    You can customize this in the **Job Settings** and expose additional directories from the host into the container.

    **Procedures are:**

    * Create a directory on host to store the collected log from container when set `cognos_cleanup_enable_log_collection` flag to `true`.

            sudo su
            mkdir /logs_tmp
            chown -R awx:awx /logs_tmp
            semanage fcontext -a -t container_file_t "/logs_tmp(/.*)?"
            restorecon -vvFR /logs_tmp

    * Create a directory to **store cognos artifacts** and copy cognos artifacts to this directory.
  
        Assume the **cognos artifacts** are located in `/home/test_aap` directory, you can specify it in the **Paths to Expose to Isolated Jobs** field

        * Note: the added directories permission are as follows:

              ls -l /home/test_aap/
              total 0
              drwxr-xr-x. 3 root root 167 Apr 23 07:37 artifacts

    * Click **Setting** -> **Job settings**
    * Set **Enable Collection(s) Downloads** -> On
    * Add **Paths to expose to isolated jobs**

            [
            "/etc/pki/ca-trust:/etc/pki/ca-trust:O",
            "/home/test_aap/artifacts:/runner/inventory/artifacts:O",
            "/logs_tmp:/runner/inventory/logs:rw",
            "/usr/share/pki:/usr/share/pki:O"
            ]

7. Add **collections_path = ./collections** in `ansible.cfg` file, and **install collections** by run local `ansible-galaxy` command.

    * Add **collections_path = ./collections** in `ansible.cfg` file on AAP installation host.

            cat /var/lib/awx/projects/cognos-ansible/ansible.cfg
            [defaults]
            inventory = hosts
            roles_path = roles
            forks = 12
            retry_files_enabled = false
            stdout_callback = yaml
            log_path = ~/.cognos_ansible.log
            any_errors_fatal = true
            host_key_checking = false
            timeout = 20
            collections_path = ./collections

    * Install collections with `ansible-galaxy` command on AAP installation host.

            cd /var/lib/awx/projects/cognos-ansible/
            ansible-galaxy collection install -r collections/requirements.yml -p ./collections

8. Run jobs/Playbooks
    * From the navigation panel, select **Resources → Templates**.
    * On the **Templates** page, click **template name** you want to run.
    * Click the `Launch` icon to start the job, you'll be redirected to the current **job execution** page, where you can view the playbook’s running log.
