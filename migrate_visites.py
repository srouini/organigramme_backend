import psycopg2
from datetime import datetime

# Define mappings: Source PG table, Target PG table, field renames, excluded fields
TABLE_MAPPINGS = [
    {
        'source_table': 'app_visite',
        'target_table': 'operation_visite',
        'field_map': {'date_visite':'date','date_creation':'created_at','validated':'valid'},
        'exclude_fields': ['gros_id','type_visite','visite'],
        'timestamped_model': True # Add this flag
    },
  
    # Add more mappings here if needed following the same structure
]

def transfer_table(source_cursor, target_cursor, mapping, current_time):
    """Transfers data for a single table based on the provided mapping."""
    source_table = mapping['source_table']
    target_table = mapping['target_table']
    field_map = mapping['field_map']
    exclude_fields = mapping['exclude_fields']
    transferred_count = 0

    try:
        print(f"--- Transferring {source_table} to {target_table} ---")
        # Fetch column names from source PostgreSQL
        source_cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = '{source_table}'
        """)
        source_columns = [col[0] for col in source_cursor.fetchall()]

        if not source_columns:
            print(f"Warning: No columns found for source table '{source_table}'. Skipping.")
            return 0

        # Fetch data from source PostgreSQL
        source_cursor.execute(f"SELECT * FROM public.\"{source_table}\"")
        rows = source_cursor.fetchall()

        if not rows:
            print(f"No data found in source table '{source_table}'. Skipping.")
            return 0

        # Prepare data for target PostgreSQL insertion
        for row in rows:
            row_data = dict(zip(source_columns, row))
            target_data = {}
            
            for source_col, value in row_data.items():
                if source_col in exclude_fields:
                    continue
                # Get the corresponding target column name
                target_col = field_map.get(source_col, source_col)
                target_data[target_col] = value
         
            # Add timestamps if required by the mapping
            if mapping.get('timestamped_model', False):
                target_data['created_at'] = current_time
                target_data['updated_at'] = current_time
                
            # Generate SQL for insertion
            columns_str = ', '.join([f'"{k}"' for k in target_data.keys()]) # Quote column names
            placeholders = ', '.join(['%s'] * len(target_data)) # Use %s for PostgreSQL
            sql = f"INSERT INTO public.\"{target_table}\" ({columns_str}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING"
            
            # Execute the insertion
            target_cursor.execute(sql, tuple(target_data.values()))
            transferred_count += 1

        print(f"Successfully prepared {transferred_count} records from '{source_table}'.")
        return transferred_count

    except psycopg2.errors.UndefinedTable:
        print(f"Error: Source table '{source_table}' not found. Skipping.")
        return 0
    except psycopg2.Error as e:
        print(f"Error inserting into target table '{target_table}': {e}. Skipping table.")
        return 0
    except Exception as e:
        print(f"An unexpected error occurred while processing table '{source_table}': {e}")
        return 0

def reset_sequence(cursor, table_name):
    """Reset the autoincrement sequence for a table after bulk insertion."""
    try:
        # Corrected SQL query to reset sequence
        sql = f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, false);"
        cursor.execute(sql)
        print(f"Successfully reset sequence for table '{table_name}'")
        return True
    except psycopg2.Error as e:
        print(f"Error resetting sequence for table '{table_name}': {e}")
        return False

def transfer_data():
    source_conn = None
    target_conn = None
    total_transferred = 0
    errors_occurred = False
    transferred_tables = []

    try:
        # Connect to source PostgreSQL database
        source_conn = psycopg2.connect(
            host="localhost",
            database="logiflow", # Source database
            user="postgres",
            password="1813830"
        )
        source_cursor = source_conn.cursor()

        # Connect to target PostgreSQL database
        target_conn = psycopg2.connect(
            host="localhost",
            database="temp", # Target database - CHANGE THIS to your target database name
            user="postgres",
            password="1813830"
        )
        target_cursor = target_conn.cursor()

        # Get current timestamp for created_at and updated_at (if needed)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for mapping in TABLE_MAPPINGS:
            try:
                count = transfer_table(source_cursor, target_cursor, mapping, current_time)
                if count > 0:
                    total_transferred += count
                    transferred_tables.append(mapping['target_table'])
                elif count == 0 and any(key in str(e) for key in ["Error:", "Warning:"] for e in [source_cursor.statusmessage]):
                    # Check if transfer_table printed an error/warning
                    if any(err_key in msg.lower() for msg in [source_cursor.statusmessage if source_cursor.statusmessage else ""] for err_key in ["error", "warning"]):
                        errors_occurred = True

            except Exception as table_e:
                print(f"Critical error during transfer setup for {mapping.get('source_table', 'N/A')}: {table_e}")
                errors_occurred = True
                # continue # Continue with next table
                # break # Stop all if one table fails critically

        # Commit changes to target PostgreSQL only if NO errors occurred
        if not errors_occurred:
            target_conn.commit()
            print(f"\nTotal records transferred across all tables: {total_transferred}")
            print("All changes committed successfully.")
            
            # Reset sequences for all transferred tables
            print("\nResetting sequences for transferred tables...")
            for table_name in transferred_tables:
                reset_sequence(target_cursor, table_name)
            target_conn.commit()
            print("All sequences reset successfully.")
        else:
            print("\nErrors occurred during transfer. Rolling back all changes.")
            target_conn.rollback()
            print(f"Total records transferred before rollback: {total_transferred}")

    except psycopg2.OperationalError as e:
        print(f"PostgreSQL connection error: {e}")
        if target_conn: target_conn.rollback()
    except psycopg2.Error as e:
        print(f"PostgreSQL error: {e}")
        if target_conn: target_conn.rollback()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        if target_conn: target_conn.rollback()
    finally:
        # Close connections
        if source_cursor: source_cursor.close()
        if source_conn: source_conn.close()
        if target_cursor: target_cursor.close()
        if target_conn: target_conn.close()
        print("Database connections closed.")

if __name__ == "__main__":
    transfer_data()