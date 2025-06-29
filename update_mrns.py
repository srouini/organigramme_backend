import psycopg2
import sqlite3
from datetime import datetime

def transfer_data():
    # Connect to PostgreSQL database

    # Connect to SQLite database
    sqlite_conn = sqlite3.connect('db.sqlite3')
    sqlite_cursor = sqlite_conn.cursor()



    try:
 
   
        sql = f"UPDATE data_mrn SET regime_id = 2 WHERE regime_id = 1"

        sqlite_cursor.execute(sql)

        # Commit changes to SQLite
        sqlite_conn.commit()
        print(f"Successfully transferred {len(rows)} records.")

    except Exception as e:
        print(f"An error occurred: {e}")
        sqlite_conn.rollback()

    finally:
        # Close connections
        sqlite_cursor.close()
        sqlite_conn.close()

if __name__ == "__main__":
    transfer_data()