### Cognos Schema definitions 
* Update if any changes are made to underlying schema

## DB: cognos

# Table: hosts
+-------------------+-----------------+------+-----+---------+-------+
| Field             | Type            | Null | Key | Default | Extra |
+-------------------+-----------------+------+-----+---------+-------+
| id                | bigint unsigned | NO   | PRI | NULL    |       |
| name              | varchar(255)    | YES  |     | NULL    |       |
| mem_capacity      | bigint unsigned | YES  |     | NULL    |       |
| host_target_ports | varchar(64)     | YES  |     | NULL    |       |
+-------------------+-----------------+------+-----+---------+-------+

# Table: mem_box
+-----------+-----------------+------+-----+---------+-------+
| Field     | Type            | Null | Key | Default | Extra |
+-----------+-----------------+------+-----+---------+-------+
| membox_id | bigint unsigned | NO   | PRI | NULL    |       |
| dev_id    | bigint unsigned | YES  |     | NULL    |       |
+-----------+-----------------+------+-----+---------+-------+

# Table: devices
+----------------+-----------------+------+-----+---------+-------+
| Field          | Type            | Null | Key | Default | Extra |
+----------------+-----------------+------+-----+---------+-------+
| dev_id         | bigint unsigned | NO   | PRI | NULL    |       |
| dev_capacity   | bigint unsigned | YES  |     | NULL    |       |
| dev_port       | int unsigned    | YES  |     | NULL    |       |
| hosts_attached | varchar(511)    | YES  |     | NULL    |       |
| status         | varchar(32)     | YES  |     | NULL    |       |
| type           | varchar(64)     | YES  |     | NULL    |       |
| mode           | varchar(64)     | YES  |     | NULL    |       |
| dev_name       | varchar(64)     | YES  |     | NULL    |       |
+----------------+-----------------+------+-----+---------+-------+

# Table: host_device_connections
+-----------+-----------------+------+-----+---------+-------+
| Field     | Type            | Null | Key | Default | Extra |
+-----------+-----------------+------+-----+---------+-------+
| host_id   | bigint unsigned | YES  |     | NULL    |       |
| host_name | varchar(128)    | YES  |     | NULL    |       |
| dev_id    | bigint unsigned | YES  |     | NULL    |       |
| dev_name  | varchar(128)    | YES  |     | NULL    |       |
+-----------+-----------------+------+-----+---------+-------+
