import psycopg2
from datetime import datetime

def transfer_data():
    # Connect to source PostgreSQL database
    source_conn = psycopg2.connect(
        host="localhost",
        database="logiflow",
        user="postgres",
        password="1813830"
    )
    source_cursor = source_conn.cursor()

    # Connect to target PostgreSQL database
    target_conn = psycopg2.connect(
        host="localhost",
        database="temp", # Target database name
        user="postgres",
        password="1813830"
    )
    target_cursor = target_conn.cursor()

    # Get current timestamp for created_at and updated_at
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        # Fetch data from source PostgreSQL
        source_cursor.execute("SELECT * FROM public.app_gros")
        rows = source_cursor.fetchall()

        # Get column names from source PostgreSQL
        source_cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'app_gros'
        """)
        columns = [col[0] for col in source_cursor.fetchall()]

        # Prepare data for target PostgreSQL insertion
        for row in rows:
            # Create a dictionary of column:value pairs
            row_data = dict(zip(columns, row))
            
            # Prepare the data for the MRN table
            # Exclude 'gros' field and rename 'accostage' to 'date_accostage'
            mrn_data = {
                k: v for k, v in row_data.items() 
                if k.lower() != 'gros'
            }
            
            # Rename 'accostage' to 'date_accostage' if it exists
            if 'accostage' in mrn_data:
                mrn_data['date_accostage'] = mrn_data.pop('accostage')
            
            # Add created_at and updated_at fields
            mrn_data['created_at'] = current_time
            mrn_data['updated_at'] = current_time

            # Generate SQL for insertion
            columns_str = ', '.join([f'"{k}"' for k in mrn_data.keys()]) # Quote column names
            placeholders = ', '.join(['%s'] * len(mrn_data)) # Use %s for PostgreSQL
            sql = f'INSERT INTO public."data_mrn" ({columns_str}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING'


            # Execute the insertion
            target_cursor.execute(sql, tuple(mrn_data.values()))

        # Commit changes to target PostgreSQL
        target_conn.commit()
        print(f"Successfully transferred {len(rows)} records.")

    except Exception as e:
        print(f"An error occurred: {e}")
        target_conn.rollback()

    finally:
        # Close connections
        source_cursor.close()
        source_conn.close()
        target_cursor.close()
        target_conn.close()

if __name__ == "__main__":
    transfer_data()