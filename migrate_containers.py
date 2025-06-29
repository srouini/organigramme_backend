import psycopg2
from psycopg2 import errors as pg_errors
from datetime import datetime
import decimal

# Define mappings: Source PG table, Target PG table, field renames, excluded fields
TABLE_MAPPINGS = [
    {
        'source_table': 'app_tc',
        'target_table': 'data_conteneur',
        'field_map': {'date_sortie_port_sec': 'date_laivrison','type_tc_id':'type_conteneur_id','tc':'matricule'},
        'exclude_fields': ['date_depotage','depote','observation_depotage','dangereux','frigo','bulletins_id','pv_reception_id','matricule_camion','date_sortie_port','date_entree_port_sec','date_sortie_port_sec','receved_by_id','etat','observation_chargement','observation_reception','observation_entree_port_sec','observation_sortie_port_sec','current_scelle_id','date_depotage','depote','observation_depotage','receved','loaded','parc_id'],
        'timestamped_model': True
    },
  
    # Add more mappings here if needed following the same structure
]

def transfer_table(source_cursor, target_cursor, mapping, current_time):
    """Transfers data for a single table, handling specific duplicate key constraints."""
    source_table = mapping['source_table']
    target_table = mapping['target_table']
    field_map = mapping.get('field_map', {})
    exclude_fields = mapping.get('exclude_fields', [])
    is_timestamped = mapping.get('timestamped_model', False)
    
    transferred_count = 0
    resolved_duplicates = 0
    skipped_rows = 0

    # Define target column names for easier access
    target_matricule_col_name = 'matricule'
    target_poids_col_name = 'poids'
    target_created_at_col_name = 'created_at'
    target_updated_at_col_name = 'updated_at'
    target_constraint_name = 'data_conteneur_matricule_article_id_30a73b3e_uniq' # Specific constraint
    max_matricule_len = 30

    try:
        print(f"--- Transferring {source_table} to {target_table} ---")
        
        # Check if we need to verify article_id existence
        check_article_id = False
        if target_table == 'data_conteneur':
            # Check if article table exists in target database
            target_cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'data_article'
                )
            """)
            article_table_exists = target_cursor.fetchone()[0]
            check_article_id = article_table_exists
            
            if check_article_id:
                print("Will check for article_id existence before inserting containers")
            else:
                print("WARNING: data_article table not found. Will not check article_id foreign key constraints.")
        
        # Fetch source column names
        source_cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = '{source_table}'
        """)
        source_columns = [col[0] for col in source_cursor.fetchall()]
        if not source_columns: raise ValueError(f"No columns found for source table {source_table}")

        # Fetch source data
        source_cursor.execute(f'SELECT * FROM public."{source_table}"')
        rows = source_cursor.fetchall()
        if not rows: print(f"No data in {source_table}. Skipping."); return 0, 0, 0

        # Process and insert rows one by one
        for row_idx, row in enumerate(rows):
            target_data = {}
            original_matricule = None # Store original for suffix generation
            
            try:
                row_data = dict(zip(source_columns, row))
                # Prepare target data dictionary
                for source_col, value in row_data.items():
                    if source_col in exclude_fields:
                        continue
                    target_col = field_map.get(source_col, source_col)
                    
                    # Store original matricule *before* potential truncation/modification
                    if target_col == target_matricule_col_name:
                        original_matricule = str(value) if value is not None else None

                    # --- Handle poids --- 
                    if target_col == target_poids_col_name:
                        processed_poids = decimal.Decimal(0)
                        if value is not None:
                            try:
                                poids_str = str(value).replace(',', '.')
                                processed_poids = decimal.Decimal(poids_str)
                            except (ValueError, TypeError, decimal.InvalidOperation):
                                print(f"Warning [Row {row_idx}]: Invalid 'poids' ({value}). Setting to 0.")
                                processed_poids = decimal.Decimal(0)
                        target_data[target_col] = processed_poids
                    # --- Handle matricule length (initial check) ---
                    elif target_col == target_matricule_col_name:
                        if value is not None:
                            str_value = str(value)
                            if len(str_value) > max_matricule_len:
                                truncated_value = str_value[:max_matricule_len]
                                print(f"Warning [Row {row_idx}]: Truncating initial 'matricule' from '{str_value}' to '{truncated_value}'.")
                                target_data[target_col] = truncated_value
                            else:
                                target_data[target_col] = value
                        else:
                            target_data[target_col] = None # Handle None matricule if necessary
                    # --- Assign other values ---
                    else:
                        target_data[target_col] = value
                
                # Add timestamps if needed
                if is_timestamped:
                    target_data[target_created_at_col_name] = current_time
                    target_data[target_updated_at_col_name] = current_time
                
                # Check if article_id exists in target database if needed
                if check_article_id and 'article_id' in target_data and target_data['article_id'] is not None:
                    article_id = target_data['article_id']
                    target_cursor.execute("SELECT EXISTS(SELECT 1 FROM data_article WHERE id = %s)", (article_id,))
                    article_exists = target_cursor.fetchone()[0]
                    
                    if not article_exists:
                        print(f"Warning [Row {row_idx}]: Article ID {article_id} does not exist in target database. Setting to NULL.")
                        target_data['article_id'] = None

                # --- Attempt Insert --- 
                columns_str = ', '.join([f'"{k}"' for k in target_data.keys()])
                placeholders = ', '.join(['%s'] * len(target_data))
                
                # Only print first few rows to avoid console spam
                if row_idx < 5 or row_idx % 1000 == 0:
                    print(target_data)
                
                sql = f'INSERT INTO public."{target_table}" ({columns_str}) VALUES ({placeholders})'
                values_tuple = tuple(target_data.values())

                try:
                    target_cursor.execute(sql, values_tuple)
                    transferred_count += 1
                    
                except pg_errors.UniqueViolation as e:
                    # Check if it's the specific constraint we want to handle
                    if target_constraint_name in str(e):
                        print(f"Info [Row {row_idx}]: Duplicate key detected ({target_constraint_name}). Trying suffixes for matricule '{original_matricule}'...")
                        inserted_with_suffix = False
                        for attempt in range(1, 11):
                            suffix = f"_dup{attempt}"
                            max_orig_len = max_matricule_len - len(suffix)
                            
                            if original_matricule is None or max_orig_len <= 0: # Cannot create unique suffix
                                print(f"Error [Row {row_idx}]: Cannot generate suffix for NULL or too-long original matricule '{original_matricule}'. Skipping.")
                                break # Break retry loop
                                
                            new_matricule = original_matricule[:max_orig_len] + suffix
                            target_data[target_matricule_col_name] = new_matricule # Update the value in the dict
                            new_values_tuple = tuple(target_data.values()) # Regenerate tuple
                            
                            try:
                                target_cursor.execute(sql, new_values_tuple) # Retry insert
                                transferred_count += 1
                                resolved_duplicates += 1
                                inserted_with_suffix = True
                                print(f"  Success: Inserted with suffixed matricule '{new_matricule}' on attempt {attempt}.")
                                break # Break retry loop on success
                            except pg_errors.UniqueViolation as retry_e:
                                if target_constraint_name in str(retry_e):
                                     # Still conflicting, try next suffix
                                     continue
                                else:
                                    # Different error on retry
                                    print(f"Error [Row {row_idx}]: Non-handled unique violation on retry attempt {attempt}: {retry_e}")
                                    break # Break retry loop
                            except Exception as retry_other_e:
                                print(f"Error [Row {row_idx}]: Unexpected error on retry attempt {attempt}: {retry_other_e}")
                                break # Break retry loop
                        
                        if not inserted_with_suffix:
                            skipped_rows += 1 # Count as skipped if all suffix attempts failed
                            print(f"Error [Row {row_idx}]: Failed to insert row for matricule '{original_matricule}' after all suffix attempts. Skipping.")
                            
                    else:
                        # Different unique constraint violation (e.g., PK 'id')
                        print(f"Warning [Row {row_idx}]: Skipping due to other unique violation: {e}")
                        skipped_rows += 1
                
                except pg_errors.ForeignKeyViolation as fk_err:
                    # Handle foreign key constraint violation
                    print(f"Warning [Row {row_idx}]: Foreign key constraint violation: {fk_err}. Skipping.")
                    skipped_rows += 1
                        
                except Exception as insert_err:
                    # Other error during initial insert attempt
                    print(f"Error [Row {row_idx}]: Skipping due to insert error: {insert_err}")
                    skipped_rows += 1

            except Exception as prep_err:
                 # Error during row preparation
                 print(f"Error [Row {row_idx}]: Skipping due to preparation error: {prep_err}")
                 skipped_rows += 1


        print(f"Finished processing for {target_table}.")

    except psycopg2.errors.UndefinedTable:
        print(f"Error: Source table '{source_table}' not found. Skipping.")
        return 0, 0, 0
    except Exception as e:
        print(f"An critical error occurred while processing table '{source_table}': {e}")
        # Re-raise to trigger rollback in the main function
        raise e 
        
    print(f"Summary for {target_table}: Inserted={transferred_count}, Resolved Duplicates={resolved_duplicates}, Skipped Rows={skipped_rows}")
    return transferred_count, resolved_duplicates, skipped_rows

def reset_sequences(target_cursor):
    """Reset the sequence for the ID column of all target tables in the mapping."""
    print("\n--- Resetting ID sequences for target tables ---")
    for mapping in TABLE_MAPPINGS:
        target_table = mapping['target_table']
        reset_sql = f"""
        SELECT setval(
            pg_get_serial_sequence('{target_table}', 'id'),
            COALESCE((SELECT MAX(id) FROM {target_table}), 0) + 1,
            false
        )
        """
        try:
            target_cursor.execute(reset_sql)
            result = target_cursor.fetchone()
            print(f"Sequence for {target_table}.id reset to {result[0]}")
        except Exception as e:
            print(f"Error resetting sequence for {target_table}.id: {e}")
    


def transfer_data():
    source_conn = None
    target_conn = None
    total_transferred = 0
    total_resolved_duplicates = 0
    total_skipped = 0
    errors_occurred = False

    # DB Configs (replace with actuals)
    source_db_config = {"host": "localhost", "database": "logiflow", "user": "postgres", "password": "1813830"}
    target_db_config = {"host": "localhost", "database": "temp", "user": "postgres", "password": "1813830"}

    try:
        source_conn = psycopg2.connect(**source_db_config)
        source_cursor = source_conn.cursor()
        target_conn = psycopg2.connect(**target_db_config)
        # Set isolation level to autocommit to avoid transaction issues
        target_conn.set_session(autocommit=True)
        target_cursor = target_conn.cursor()
        current_time = datetime.now()

        for mapping in TABLE_MAPPINGS:
            table_transferred = 0
            table_resolved = 0
            table_skipped = 0
            try:
                table_transferred, table_resolved, table_skipped = transfer_table(source_cursor, target_cursor, mapping, current_time)
                total_transferred += table_transferred
                total_resolved_duplicates += table_resolved
                total_skipped += table_skipped
                if table_skipped > 0:
                     print(f"NOTE: {table_skipped} rows were skipped during transfer for {mapping.get('target_table')}")
                     # errors_occurred = True # Decide if skipping rows is a critical error

            except Exception as table_e:
                print(f"CRITICAL error processing table {mapping.get('target_table', 'N/A')}: {table_e}. Continuing with next table.")
                errors_occurred = True
                # Don't break here, continue with next table
                
        # Reset sequences for all tables after data transfer
        reset_sequences(target_cursor)

        # No need for commit/rollback with autocommit mode
        print("\n--- Transfer Complete --- ")
        print(f"Total records inserted: {total_transferred}")
        print(f"Total duplicates resolved: {total_resolved_duplicates}")
        print(f"Total rows skipped (errors/unresolved duplicates): {total_skipped}")
        if errors_occurred:
            print("Some errors occurred during transfer. Check the logs for details.")
        else:
            print("All tables processed successfully.")

    # Error handling and finally block remain similar ...
    except psycopg2.OperationalError as e:
        print(f"PostgreSQL connection error: {e}")
    except psycopg2.Error as e:
        print(f"PostgreSQL error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in transfer_data: {e}")
    finally:
        if source_cursor: source_cursor.close()
        if source_conn: source_conn.close()
        if target_cursor: target_cursor.close()
        if target_conn: target_conn.close()
        print("Database connections closed.")

if __name__ == "__main__":
    transfer_data()