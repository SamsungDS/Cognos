import hashlib
import os
import sqlite3
from pathlib import Path
from typing import List, Any


class SqliteClient():
    def __init__(self, svk_data_path="/var/lib/svk", mock=False, in_mem=False,
                 logger=None):
        self.logger = logger
        self.in_mem_mode = in_mem
        self.db_file_path = svk_data_path + os.sep + 'cognos.db'

    def get_db_fingerpint(self):
        path = Path(self.db_file_path)
        hash = hashlib.new("sha256")
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash.update(chunk)
        return hash.hexdigest()

    def get_db_info(self):
        db_fingerprint = self.get_db_fingerpint()
        self.logger.debug("SQL Client DB \n")
        self.logger.debug(f"In memory mode: {self.in_mem_mode}\n")
        self.logger.debug(f"DB File Path: {self.db_file_path}\n")
        self.logger.debug(f"DB Fingerprint: {db_fingerprint}\n")

    def get_sqlite_connection(self):
        conn = None
        if self.in_mem_mode:
            conn = sqlite3.connect(':memory:', check_same_thread=False)
        else:
            conn = sqlite3.connect(self.db_file_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")

        def trace(sql):
            self.logger.debug(f"SQL DEBUG: {sql}")
        conn.set_trace_callback(trace)
        return conn

    def table_description(self, table_name: str) -> None:
        """
        Displays Schema Description of Table
        """
        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name});")
            cols = cursor.fetchall()
            self.logger.info(f"{table_name} DESCRIPTION: ")
            for column in cols:
                self.logger.info(column)
            self.logger.info("\n")

    def get_table_records(self, table_name: str) -> None:
        """
        Displays contents of Table
        """
        with self.get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table_name}")
            records = cursor.fetchall()
            self.logger.info(f"TABLE: {table_name}")
            for record in records:
                self.logger.info(record)
            self.logger.info("\n")

    def exec_query(self, query: str, params: tuple) -> None:
        """
        Executes query with no return, used for insert/delets primarily
        """
        with self.get_sqlite_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
            except sqlite3.Error as error:
                self.logger.critical(
                    "Sqlite3 Error - cognos DB: \n"
                    f"QUERY: {query} \n"
                    f"ERROR: {error} \n"
                )
            except Exception as error:
                self.logger.critical(
                    "Exception - cognos DB: \n"
                    f"QUERY: {query} \n"
                    f"ERROR: {error} \n"
                )

    def exec_fetch_query(self, query: str, params: tuple) -> List:
        """
        Executes read query with parameters and returns all records
        """
        with self.get_sqlite_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(query, params)
                res = cursor.fetchall()
                return res
            except sqlite3.Error as error:
                self.logger.critical(
                    "Sqlite3 Error - cognos DB: \n"
                    f"QUERY: {query} \n"
                    f"ERROR: {error} \n"
                )
                return None
            except Exception as error:
                self.logger.critical(
                    "Exception - cognos DB: \n"
                    f"QUERY: {query} \n"
                    f"ERROR: {error} \n"
                )
                return None

    def exec_fetch_singlerecord_query(self, query: str, params: tuple) -> Any:
        """
        Executes read query and returns a single value

        Useful for count operations or finding a single
        corresponding attribute
        """
        with self.get_sqlite_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(query, params)
                res = cursor.fetchone()[0]
                return res
            except sqlite3.Error as error:
                self.logger.critical(
                    "Sqlite3 Error - cognos DB: \n"
                    f"QUERY: {query} \n"
                    f"ERROR: {error} \n"
                )
                return None
            except Exception as error:
                self.logger.critical(
                    "Exception - cognos DB: \n"
                    f"QUERY: {query} \n"
                    f"ERROR: {error} \n"
                )
                return None

    def execute_query(self, query: str) -> Any:
        """
        Performs execution query with no parameters with DB commit
        and returns results
        """
        with self.get_sqlite_connection() as conn:
            try:
                cursor = conn.cursor()
                result = cursor.execute(query)
                conn.commit()
                return result
            except sqlite3.Error as error:
                self.logger.critical(
                    "Failed to connect to sqlite3 - cognos DB: %s",
                    error
                )
                return None
            except Exception as error:
                self.logger.critical("Error: %s", error)
                return None

    def count_query(self, query):
        with self.get_sqlite_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(query)
                return cursor.fetchone()[0]
            except sqlite3.Error as error:
                self.logger.critical(
                    "Failed to connect to sqlite3 - cognos DB: %s",
                    error
                )
                return None
            except Exception as error:
                self.logger.critical("Error: %s", error)
                return None
