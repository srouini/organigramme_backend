import psycopg2
import sqlite3
from datetime import datetime

# Define mappings: PG table, SQLite table, field renames, excluded PG fields
# Assumes standard Django naming for tables not explicitly mentioned (app_model)
TABLE_MAPPINGS = [
    {
        'pg_table': 'bareme_regime',
        'sqlite_table': 'bareme_regime',
        'field_map': {'methode_calcule': 'methode_de_calcule','color':'couleur'},
        'exclude_fields': ['enterposage','parc','parc_id'],
        'timestamped_model': False
    },
    {
        'pg_table': 'app_gros',
        'sqlite_table': 'data_mrn',
        'field_map': {'accostage': 'date_accostage'},
        'exclude_fields': ['gros'],
        'timestamped_model': True # Add this flag
    },
    {
        'pg_table': 'app_article',
        'sqlite_table': 'data_article',
        'field_map': {'gros_id': 'mrn_id'},
        'exclude_fields': ['groupage','date_depotage','depote','observation_depotage',],
        'timestamped_model': True # Add this flag
    },

    # Add more mappings here if needed following the same structure
]

def transfer_table(pg_cursor, sqlite_cursor, mapping, current_time):
    """Transfers data for a single table based on the provided mapping."""
    pg_table = mapping['pg_table']
    sqlite_table = mapping['sqlite_table']
    field_map = mapping['field_map']
    exclude_fields = mapping['exclude_fields']
    transferred_count = 0

    try:
        print(f"--- Transferring {pg_table} to {sqlite_table} ---")
        # Fetch column names from PostgreSQL
        pg_cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = '{pg_table}'
        """)
        pg_columns = [col[0] for col in pg_cursor.fetchall()]

        if not pg_columns:
            print(f"Warning: No columns found for PostgreSQL table '{pg_table}'. Skipping.")
            return 0

        # Fetch data from PostgreSQL
        pg_cursor.execute(f"SELECT * FROM public.\"{pg_table}\"") # Quote table name
        rows = pg_cursor.fetchall()

        if not rows:
            print(f"No data found in PostgreSQL table '{pg_table}'. Skipping.")
            return 0

        # Prepare data for SQLite insertion
        for row in rows:
            row_data = dict(zip(pg_columns, row))
            sqlite_data = {}

            # Debug print before the loop
            print(f"DEBUG: Processing row. exclude_fields = {exclude_fields}")

            for pg_col, value in row_data.items():
                # Debug print inside the loop
                print(f"DEBUG: Checking column '{pg_col}' (type: {type(pg_col)})")
                if pg_col in exclude_fields:
                    print(f"DEBUG: >>> Excluding '{pg_col}' based on exclude_list.")
                    continue
                # Get the corresponding SQLite column name
                sqlite_col = field_map.get(pg_col, pg_col)
                print(f"DEBUG: --- Adding to sqlite_data: '{sqlite_col}'") # Debug print before adding
                sqlite_data[sqlite_col] = value

            # Conditionally add created_at and updated_at
            if mapping.get('timestamped_model', False):
                sqlite_data['created_at'] = current_time
                sqlite_data['updated_at'] = current_time

            # User's existing print statement
            print("Final sqlite_data before SQL generation:", sqlite_data)

            # Generate SQL for insertion - Use standard double quotes
            columns_str = ', '.join([f'"{k}"' for k in sqlite_data.keys()]) # Use "{k}"
            placeholders = ', '.join(['?'] * len(sqlite_data))
            sql = f"INSERT INTO \"{sqlite_table}\" ({columns_str}) VALUES ({placeholders})" # Table name quoting is fine

            # Execute the insertion
            try:
                sqlite_cursor.execute(sql, tuple(sqlite_data.values()))
                transferred_count += 1
            except sqlite3.Error as insert_err: # Catch any SQLite error during insert
                 print(f"ERROR during SQLite INSERT for table '{sqlite_table}'.")
                 print(f"  SQL: {sql}")
                 # Be careful printing raw data if it's very large or sensitive
                 # print(f"  Data: {sqlite_data}") 
                 print(f"  Problematic Keys: {list(sqlite_data.keys())}") # Print keys instead of full data
                 print(f"  Error: {insert_err}")
                 # Decide how to handle: skip row, skip table, or raise error?
                 # For now, let's print and continue to the next row to see if others work.
                 errors_occurred_in_table = True # Flag an error for this table
                 continue # Skip this row and try the next one
            except Exception as general_insert_err: # Catch other potential errors during execute
                print(f"UNEXPECTED ERROR during SQLite INSERT for table '{sqlite_table}'.")
                print(f"  SQL: {sql}")
                print(f"  Problematic Keys: {list(sqlite_data.keys())}")
                print(f"  Error: {general_insert_err}")
                errors_occurred_in_table = True
                continue # Skip row

        # After the loop, check if any errors occurred within this table
        if 'errors_occurred_in_table' in locals() and errors_occurred_in_table:
             print(f"Warning: One or more rows failed to insert into '{sqlite_table}'. See errors above.")
             # Decide if this table failure should prevent commit (return 0 or less)
             # return 0 # Indicate failure if any row fails

        print(f"Successfully prepared {transferred_count} records from '{pg_table}'.")
        return transferred_count

    except psycopg2.errors.UndefinedTable:
        print(f"Error: PostgreSQL table '{pg_table}' not found. Skipping.")
        return 0
    except sqlite3.OperationalError as e:
        print(f"Error inserting into SQLite table '{sqlite_table}': {e}. Skipping table.")
        # Attempt to rollback partial inserts for this specific table if needed, 
        # but main commit/rollback is outside
        return 0 # Indicate failure for this table
    except Exception as e:
        print(f"An unexpected error occurred while processing table '{pg_table}': {e}")
        return 0

def transfer_data():
    pg_conn = None
    sqlite_conn = None
    total_transferred = 0
    errors_occurred = False

    try:
        # Connect to PostgreSQL database
        pg_conn = psycopg2.connect(
            host="localhost",
            database="logiflow", # Make sure this is your PG database name
            user="postgres",    # Make sure this is your PG user
            password="1813830"   # Use environment variables or config in production!
        )
        pg_cursor = pg_conn.cursor()

        # Connect to SQLite database
        sqlite_conn = sqlite3.connect('_db.sqlite3')
        sqlite_cursor = sqlite_conn.cursor()

        # Get current timestamp for created_at and updated_at
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for mapping in TABLE_MAPPINGS:
            try:
                count = transfer_table(pg_cursor, sqlite_cursor, mapping, current_time)
                if count > 0:
                    total_transferred += count
                elif count == 0 and any(key in str(e) for key in ["Error:", "Warning:"] for e in [pg_cursor.statusmessage]): # Basic check if error/warning occurred in transfer_table
                     # Check if transfer_table printed an error/warning (simplistic check)
                    # A more robust way would be for transfer_table to return a status tuple (count, success_flag)
                    # For now, we assume if count is 0 after an error print, it's an error state.
                    # We check common error keywords printed by transfer_table
                    # Need a better mechanism if precise error tracking per table is vital
                    if any(err_key in msg.lower() for msg in [pg_cursor.statusmessage if pg_cursor.statusmessage else ""] for err_key in ["error", "warning"]):
                        errors_occurred = True

            except Exception as table_e:
                print(f"Critical error during transfer setup for {mapping.get('pg_table', 'N/A')}: {table_e}")
                errors_occurred = True
                # Decide if you want to stop all transfers or continue with the next table
                # continue 
                # break # Stop all if one table fails critically before processing

        # Commit changes to SQLite only if NO errors occurred during processing any table
        if not errors_occurred:
            sqlite_conn.commit()
            print(f"\nTotal records transferred across all tables: {total_transferred}")
            print("All changes committed successfully.")
        else:
            print("\nErrors occurred during transfer. Rolling back all changes.")
            sqlite_conn.rollback()
            print(f"Total records transferred before rollback: {total_transferred}") # This might be non-zero if some tables succeeded before an error

    except psycopg2.OperationalError as e:
        print(f"PostgreSQL connection error: {e}")
        if sqlite_conn: sqlite_conn.rollback() # Rollback if connection established
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        # Rollback might not be needed if connection failed, but doesn't hurt
        if sqlite_conn: sqlite_conn.rollback()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        if sqlite_conn: sqlite_conn.rollback()
    finally:
        # Close connections
        if pg_cursor: pg_cursor.close()
        if pg_conn: pg_conn.close()
        if sqlite_cursor: sqlite_cursor.close()
        if sqlite_conn: sqlite_conn.close()
        print("Database connections closed.")

if __name__ == "__main__":
    transfer_data()