import psycopg2
from datetime import datetime
import io
import csv

# Define mappings: PG table, PG table, field renames, excluded PG fields
# Assumes standard Django naming for tables not explicitly mentioned (app_model)
TABLE_MAPPINGS = [
    # {
    #     'pg_table': 'bareme_regime',
    #     'sqlite_table': 'bareme_regime',
    #     'field_map': {'methode_calcule': 'methode_de_calcule','color':'couleur'},
    #     'exclude_fields': ['enterposage','parc','parc_id'],
    #     'timestamped_model': False
    # },
    # {
    #     'pg_table': 'app_gros',
    #     'sqlite_table': 'data_mrn',
    #     'field_map': {'accostage': 'date_accostage'},
    #     'exclude_fields': ['gros'],
    #     'timestamped_model': True # Add this flag
    # },
    # {
    #     'pg_table': 'app_article',
    #     'sqlite_table': 'data_article',
    #     'field_map': {'gros_id':'mrn_id'},
    #     'exclude_fields': ['groupage','date_depotage','depote','observation_depotage'],
    #     'timestamped_model': True # Add this flag
    # },
    {
        'pg_table': 'app_tc',
        'sqlite_table': 'data_conteneur',
        'field_map': {'date_sortie_port_sec': 'date_laivrison','type_tc_id':'type_conteneur_id','tc':'matricule'},
        'exclude_fields': ['date_depotage','depote','observation_depotage','dangereux','frigo','bulletins_id','pv_reception_id','matricule_camion','date_sortie_port','date_entree_port_sec','date_sortie_port_sec','receved_by_id','etat','observation_chargement','observation_reception','observation_entree_port_sec','observation_sortie_port_sec','current_scelle_id','date_depotage','depote','observation_depotage','receved','loaded','parc_id'],
        'timestamped_model': True # Add this flag
    },
    # {
    #     'pg_table': 'app_sousarticle',
    #     'sqlite_table': 'data_sousarticle',
    #     'field_map': {'tc_id': 'conteneur_id','box_id':'position_id','invoiced':'billed'},
    #     'exclude_fields': ['dangereux','description','unite_de_visite','unite_de_chargement','unite_de_magasinage'],
    #     'timestamped_model': True # Add this flag
    # },
    # {
    #     'pg_table': 'app_scelle',
    #     'sqlite_table': 'data_scelle',
    #     'field_map': {'tc_id': 'conteneur_id','type_scelle':'type','date_creation':'date'},
    #     'exclude_fields': ['date_creation'],
    #     'timestamped_model': True # Add this flag
    # },

    # Add more mappings here if needed following the same structure
]

def transfer_table(source_cursor, target_cursor, mapping, current_time):
    """Transfers data for a single table based on the provided mapping."""
    source_table = mapping['pg_table']
    target_table = mapping['sqlite_table']
    field_map = mapping['field_map']
    exclude_fields = mapping['exclude_fields']
    add_timestamps = mapping.get('timestamped_model', False)
    
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

        # Build the target column list considering mappings and exclusions
        target_columns = []
        source_to_target_idx = {}
        
        for i, col in enumerate(source_columns):
            if col in exclude_fields:
                continue
            
            target_col = field_map.get(col, col)
            target_columns.append(target_col)
            source_to_target_idx[i] = len(target_columns) - 1
        
        # Add timestamp columns if needed
        if add_timestamps:
            target_columns.append('created_at')
            target_columns.append('updated_at')
        
        # Create in-memory CSV buffer for COPY
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        
        # Process and write each row to the buffer
        for row in rows:
            # Create a new record with only the target columns
            target_row = [None] * len(target_columns)
            
            # Map source values to target positions
            for source_idx, target_idx in source_to_target_idx.items():
                if source_idx < len(row):
                    target_row[target_idx] = row[source_idx]
            
            # Add timestamp values if needed
            if add_timestamps:
                target_row[-2] = current_time  # created_at
                target_row[-1] = current_time  # updated_at
                
            # Write the row to the CSV buffer
            csv_writer.writerow(target_row)
            transferred_count += 1
        
        # Prepare for COPY operation
        csv_buffer.seek(0)
        columns_str = ', '.join([f'"{col}"' for col in target_columns])
        
        # Perform the COPY operation
        target_cursor.copy_expert(
            f"COPY public.\"{target_table}\" ({columns_str}) FROM STDIN WITH CSV",
            csv_buffer
        )
        
        print(f"Successfully prepared {transferred_count} records from '{source_table}'.")
        return transferred_count

    except psycopg2.errors.UndefinedTable as e:
        print(f"Error: Table not found: {e}. Skipping.")
        return 0
    except psycopg2.Error as e:
        print(f"PostgreSQL error: {e}. Skipping table.")
        return 0
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return 0

def transfer_data():
    source_conn = None
    target_conn = None
    total_transferred = 0
    errors_occurred = False
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
            database="temp", # Target database
            user="postgres",
            password="1813830"
        )
        
        # Disable triggers/constraints for the entire session
        print("Disabling triggers/constraints...")
        target_cursor = target_conn.cursor()
        target_cursor.execute("SET session_replication_role = 'replica';")
        target_conn.commit() # Commit the session setting

        # Truncate all target tables *before* starting data transfer
        print("\nTruncating all target tables...")
        for mapping in TABLE_MAPPINGS:
            target_table_name = mapping["sqlite_table"]
            print(f"Truncating {target_table_name}...")
            try:
                # Using CASCADE because we are truncating all dependent tables defined in MAPPINGS
                target_cursor.execute(f'TRUNCATE TABLE public."{target_table_name}" RESTART IDENTITY CASCADE')
            except (Exception, psycopg2.Error) as trunc_error:
                print(f"Error truncating table {target_table_name}: {trunc_error}")
                target_conn.rollback() # Rollback potential partial truncates
                raise # Re-raise the error to stop migration if truncation fails
        target_conn.commit() # Commit successful truncations
        print("Truncation complete.")

        # --- Main Data Transfer Loop ---
        print("\nStarting data transfer...")
        for mapping in TABLE_MAPPINGS:
            print(f"\nProcessing table: {mapping['pg_table']} -> {mapping['sqlite_table']}")
            try:
                count = transfer_table(source_cursor, target_cursor, mapping, current_time)
                if count > 0:
                    total_transferred += count
                    print(f"Successfully transferred {count} records for {mapping['sqlite_table']}.")
                else:
                    print(f"No records transferred for {mapping['sqlite_table']}.")
                
                target_conn.commit() # Commit after each table transfer
                print(f"Committed changes for {mapping['sqlite_table']}.")

            except Exception as table_e:
                print(f"ERROR processing table {mapping.get('pg_table', 'N/A')}: {table_e}")
                target_conn.rollback() # Rollback current table transaction
                errors_occurred = True
            
        # Re-enable triggers/constraints after all tables are processed
        print("\nRe-enabling triggers/constraints...")
        target_cursor.execute("SET session_replication_role = 'origin';")
        target_conn.commit()

        print(f"\nTotal records transferred across all tables: {total_transferred}")
        if errors_occurred:
            print("Some tables encountered errors and were rolled back. See logs above.")
        else:
            print("All changes committed successfully.")

    except psycopg2.OperationalError as e:
        print(f"PostgreSQL connection error: {e}")
    except psycopg2.Error as e:
        print(f"PostgreSQL error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # Close connections
        if source_cursor: source_cursor.close()
        if source_conn: source_conn.close()
        if target_conn: target_conn.close()
        print("Database connections closed.")

if __name__ == "__main__":
    transfer_data()