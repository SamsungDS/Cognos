import os
import sqlite3
from threading import Lock
from typing import List, Any


class SqliteClient():
    def __init__(self, svk_data_path="/var/lib/svk", mock=False):
        if mock:
            svk_data_path = os.getcwd()
        db_file = svk_data_path + os.sep + 'cognos.db'
        if os.path.exists(svk_data_path):
            if os.path.exists(db_file):
                # we must load sqlite db from scratch every time CAL runs
                os.remove(db_file)
        else:
            # create data directory
            os.makedirs(svk_data_path)

        self.connection = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.connection.cursor()

        # Sqlite doesn't like to be used in multi-threaded use cases.
        # Since we are running in the context of Flask webserver,
        # we must make sure that SQL operations are not run concurrently.
        self.lock = Lock()

    def __del__(self):
        # terminate connection upon deconstruction
        if self.connection:
            self.connection.close()
            print("connection to cognos DB is closed")

    def table_description(self, table_name: str) -> None:
        """
        Displays Schema Description of Table
        """
        self.lock.acquire(True)
        self.cursor.execute(f"PRAGMA table_info({table_name});")
        cols = self.cursor.fetchall()
        print(f"{table_name} DESCRIPTION: ")
        for column in cols:
            print(column)
        print("\n")
        self.lock.release()

    def get_table_records(self, table_name: str) -> None:
        """
        Displays contents of Table
        """
        self.lock.acquire(True)
        self.cursor.execute(f"SELECT * FROM {table_name}")
        records = self.cursor.fetchall()
        print(f"TABLE: {table_name}")
        for record in records:
            print(record)
        print("\n")
        self.lock.release()

    def exec_query(self, query: str, params: tuple) -> None:
        """
        Executes query with no return, used for insert/delets primarily
        """
        try:
            self.lock.acquire(True)
            self.cursor.execute(query, params)
            self.connection.commit()
        except sqlite3.Error as error:
            print(
                "Sqlite3 Error - cognos DB: \n"
                f"QUERY: {query} \n"
                f"ERROR: {error} \n"
            )
        except Exception as error:
            print(
                "Exception - cognos DB: \n"
                f"QUERY: {query} \n"
                f"ERROR: {error} \n"
            )
        finally:
            self.lock.release()

    def exec_fetch_query(self, query: str, params: tuple) -> List:
        """
        Executes read query with parameters and returns all records
        """
        try:
            self.lock.acquire(True)
            self.cursor.execute(query, params)
            res = self.cursor.fetchall()
            return res
        except sqlite3.Error as error:
            print(
                "Sqlite3 Error - cognos DB: \n"
                f"QUERY: {query} \n"
                f"ERROR: {error} \n"
            )
            return None
        except Exception as error:
            print(
                "Exception - cognos DB: \n"
                f"QUERY: {query} \n"
                f"ERROR: {error} \n"
            )
            return None
        finally:
            self.lock.release()

    def exec_fetch_singlerecord_query(self, query: str, params: tuple) -> Any:
        """
        Executes read query and returns a single value

        Useful for count operations or finding a single
        corresponding attribute
        """
        try:
            self.lock.acquire(True)
            self.cursor.execute(query, params)
            res = self.cursor.fetchone()[0]
            return res
        except sqlite3.Error as error:
            print(
                "Sqlite3 Error - cognos DB: \n"
                f"QUERY: {query} \n"
                f"ERROR: {error} \n"
            )
            return None
        except Exception as error:
            print(
                "Exception - cognos DB: \n"
                f"QUERY: {query} \n"
                f"ERROR: {error} \n"
            )
            return None
        finally:
            self.lock.release()

    def execute_query(self, query: str) -> Any:
        """
        Performs execution query with no parameters with DB commit
        and returns results
        """
        try:
            self.lock.acquire(True)
            result = self.cursor.execute(query)
            self.connection.commit()
            return result
        except sqlite3.Error as error:
            print("Failed to connect to sqlite3 - cognos DB: ", error)
            return None
        except Exception as error:
            print("Error: ", error)
            return None
        finally:
            self.lock.release()

    def count_query(self, query):
        try:
            self.lock.acquire(True)
            self.cursor.execute(query)
            return self.cursor.fetchone()[0]
        except sqlite3.Error as error:
            print("Failed to connect to sqlite3 - cognos DB: ", error)
            return None
        except Exception as error:
            print("Error: ", error)
            return None
        finally:
            self.lock.release()
