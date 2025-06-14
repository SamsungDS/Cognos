### Cognos Schema definitions 
* Update if any changes are made to underlying schema

## DB: cognos (in-memory only)

# Table: hosts
+-------------------+-----------------+------+-----+---------+-------+
| Field             | Type            | Null | Key | Default | Extra |
+-------------------+-----------------+------+-----+---------+-------+
| node_name         | varchar(255)    | NO   | PRI | NULL    |       |
| fm_type           | varchar(32)     | YES  |     | NULL    |       |
| mem_capacity      | bigint unsigned | YES  |     | NULL    |       |
| target_ports      | varchar(64)     | YES  |     | NULL    |       |
| ip_addr           | varchar(32)     | YES  |     | NULL    |       |
| hostname          | varchar(255)    | YES  |     | NULL    |       |
| remote_id         | bigint unsigned | YES  |     | NULL    |       |
+-------------------+-----------------+------+-----+---------+-------+

# Table: devices
+----------------+-----------------+------+-----+---------+-------+
| Field          | Type            | Null | Key | Default | Extra |
+----------------+-----------------+------+-----+---------+-------+
| id             | bigint unsigned | NO   | PRI | NULL    |       |
| mem_capacity   | bigint unsigned | YES  |     | NULL    |       |
| port           | int unsigned    | YES  |     | NULL    |       |
| type           | varchar(32)     | YES  |     | NULL    |       |
| mode           | varchar(15)     | YES  |     | NULL    |       |
| name           | varchar(32)     | YES  |     | NULL    |       |
+----------------+-----------------+------+-----+---------+-------+

# Table: connections
+---------------+-----------------+------+-----+---------+-------+
| Field         | Type            | Null | Key | Default | Extra |
+---------------+-----------------+------+-----+---------+-------+
| cluster_name  | varchar(64)     | YES  |     | NULL    |       |
| node_name     | varchar(255)    | YES  |     | NULL    |       |
| device_id     | bigint unsigned | YES  |     | NULL    |       |
+---------------+-----------------+------+-----+---------+-------+
