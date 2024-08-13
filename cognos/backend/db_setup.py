import mysql.connector


def create_database(db_name):
    connection = mysql.connector.connect(
        host="localhost",
        user="dev",
        passwd="CXL123mem!"
    )
    cursor = connection.cursor()

    if not check_db_exists(db_name, cursor):
        cursor.execute(f"CREATE DATABASE {db_name}")
        if not check_db_exists(db_name, cursor):
            raise Exception(f"Unable to create Mysql DB: {db_name}")
    connection.close()
    return get_database_connection(db_name)


def check_db_exists(db_name, cursor):
    cursor.execute("SHOW DATABASES")
    db_exists = False
    for x in cursor.fetchall():
        if db_name == x[0]:
            db_exists = True
            break
    return db_exists


def get_database_connection(db_name):
    db = mysql.connector.connect(
        host="localhost",
        user="dev",
        passwd="CXL123mem!",
        database=db_name
    )
    return db, db.cursor()


def setup_devices_table(db, cursor):
    create_devices_table = (
        "CREATE TABLE IF NOT EXISTS devices ("
        "dev_id BIGINT UNSIGNED NOT NULL, "
        "dev_capacity BIGINT UNSIGNED, "
        "dev_port INT UNSIGNED, "
        "hosts_attached VARCHAR(511), "
        "status VARCHAR(32), "
        "type VARCHAR(64), "
        "mode VARCHAR(64), "
        "dev_name VARCHAR(64), "
        "used_capacity_units VARCHAR(10), "
        "device_type VARCHAR(32), "
        "PRIMARY KEY (dev_id));"
    )
    cursor.execute(create_devices_table)
    db.commit()


def setup_host_device_connections_table(db, cursor):
    create_host_device_connections_table = (
        "CREATE TABLE IF NOT EXISTS host_device_connections ("
        "host_id BIGINT UNSIGNED, "
        "host_name VARCHAR(128), "
        "dev_id BIGINT UNSIGNED, "
        "dev_name VARCHAR(128)"
        ");"
    )
    cursor.execute(create_host_device_connections_table)
    db.commit()


def setup_hosts_table(db, cursor):
    create_hosts_table = (
        "CREATE TABLE IF NOT EXISTS hosts ("
        "id BIGINT UNSIGNED NOT NULL, "
        "name VARCHAR(255), "
        "mem_capacity BIGINT UNSIGNED, "
        "hosts_target_ports VARCHAR(64), "
        "PRIMARY KEY (id));"
    )
    cursor.execute(create_hosts_table)
    db.commit()


def setup_mem_box_table(db, cursor):
    create_membox_table = (
        "CREATE TABLE IF NOT EXISTS mem_box ("
        "membox_id BIGINT UNSIGNED NOT NULL, "
        "name VARCHAR(255), "
        "mem_capacity BIGINT UNSIGNED, "
        "hosts_target_ports VARCHAR(64), "
        "PRIMARY KEY (membox_id));"
    )
    cursor.execute(create_membox_table)
    db.commit()


def shutdown_db_connection(db):
    db.close()


if __name__ == "__main__":
    """create and setup database for Samsung Cognos Management Console """

    db_name = "cognos"
    db, cursor = create_database(db_name)

    setup_host_device_connections_table(db, cursor)
    setup_hosts_table(db, cursor)
    setup_devices_table(db, cursor)
    setup_mem_box_table(db, cursor)

    shutdown_db_connection(db)
