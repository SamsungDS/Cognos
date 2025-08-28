from typing import Dict, List
from cognos.backend.sqlite_client import SqliteClient


class Node():
    def __init__(self, sql_client: SqliteClient, node_name: str, fm_type: str,
                 mem_capacity: int, target_ports: List[int], ip_addr: str,
                 hostname: str, remote_id: int):
        self.sql_client = sql_client
        self.node_name = node_name
        self.fm_type = fm_type
        self.mem_capacity = mem_capacity
        self.target_ports = target_ports
        self.ip_addr = ip_addr
        self.hostname = hostname
        self.remote_id = remote_id

    def __repr__(self) -> Dict:
        """
        Used to print out or display Node object
        """
        return (
            f"Node: {self.node_name}\n"
            f"fm_type: {self.fm_type}\n"
            f"mem_capacity: {self.mem_capacity}\n"
            f"target_ports: {self.target_ports}\n"
            f"ip_addr: {self.ip_addr}\n"
            f"hostname: {self.hostname}\n"
            f"remote_id: {self.remote_id}\n"
        )

    def insert_node_into_hosts_table(self) -> None:
        """
        Serializes Node Object and inserts it into hosts table
        """
        with self.sql_client.get_sqlite_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO hosts "
                    "(node_name, fm_type, mem_capacity, target_ports, "
                    "ip_addr, hostname, remote_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (self.node_name, self.fm_type, self.mem_capacity,
                     self.target_ports, self.ip_addr, self.hostname,
                     self.remote_id)
                )
                conn.commit()
            except Exception as error:
                print(f"Failed to insert node into hosts table: {str(error)}")
