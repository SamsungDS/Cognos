# Cognos

Cognos is a management console for CXL memory devices and tiered memory. This repository brings the Cognos software stack together in one place.

The repository is being assembled. At present it contains the deployment automation; the other components are added as they are imported.

## Repository layout

| Path | Contents |
|---|---|
| `deploy/` | Ansible playbooks and roles that deploy Cognos. Imported from the cognos-ansible repository with its history. |

## Deploy Cognos using Ansible

To deploy Cognos using Ansible, follow [deploy/README.md](deploy/README.md). It covers, in order:

1. Creating the Ansible user on the cluster nodes and the controller.
2. Setting up the Ansible controller.
3. Writing the inventory file.
4. Storing passwords with `ansible-vault`.
5. Preparing the Cognos packages in `deploy/artifacts/`.
6. Running the deployment playbook.

In short, once the prerequisites are in place:

```bash
cd deploy
ansible-playbook -i your_inventory playbooks/deploy_cognos.yml --ask-vault-pass
```

### Passwords to set before deploying

The repository does not contain working passwords. Two variables in `deploy/group_vars/all/all.yml` hold placeholder values and must be replaced before Cognos is deployed:

| Variable | Used for | Placeholder |
|---|---|---|
| `influxdb_pwd` | Password of the InfluxDB user (`influxdb_user`, default `svk`) created when InfluxDB is set up on the management server. | `CHANGE_ME_INFLUXDB_PASSWORD` |
| `rbac_password` | Password of the RBAC super administrator (`rbac_username`, default `super_admin`). Written to the RBAC service configuration as `SUPER_ADMIN_PASSWORD`. It must be at least 8 characters. | `CHANGE_ME_RBAC_PASSWORD` |

Do not put real values in `all.yml` and do not commit them. Add them to the vault file that holds the Ansible user's password, `deploy/group_vars/all/passwords.yml` (section IV of [deploy/README.md](deploy/README.md)):

```bash
cd deploy
ansible-vault edit group_vars/all/passwords.yml    # use "ansible-vault create" if the file does not exist yet
```

```yaml
---
vault_ansible_password: "<your_ansible_password>"
influxdb_pwd: "<your_influxdb_password>"
rbac_password: "<your_rbac_password>"
```

Ansible loads the files in `group_vars/all/` in alphabetical order, so the values in `passwords.yml` override the placeholders in `all.yml`.

Other ways to supply the values:

- Pass an encrypted variables file with the same content: `ansible-playbook ... -e @secrets.yml --ask-vault-pass`.
- In automation, write the three variables to `group_vars/all/passwords.yml` from protected, masked CI variables before running the playbook.

The placeholders are not rejected automatically. If they are left unchanged, the InfluxDB user and the RBAC administrator are created with these placeholder passwords.
