import sqlite3
import pandas as pd
import io
import os
import streamlit as st
from typing import List, Tuple, Dict, Optional

# Create persistent DB directory if it doesn't exist
PERSISTENT_DB_DIR = "custom_dbs"
os.makedirs(PERSISTENT_DB_DIR, exist_ok=True)

# ================= FILE UPLOAD FUNCTIONS =================

def add_tables_to_existing_sqlite(
    db_path: str,
    files_data: List[Tuple[bytes, str]]
) -> Tuple[bool, str, List[str]]:
    """
    Add new tables to an existing SQLite database
    
    Args:
        db_path: Path to existing database
        files_data: List of tuples (file_bytes, filename)
    
    Returns:
        (success, message, table_names_added)
    """
    try:
        # Connect to existing database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        table_names_added = []
        tables_info = []
        
        # Process each file
        for file_bytes, filename in files_data:
            try:
                # Read file based on extension
                if filename.endswith('.csv'):
                    df = pd.read_csv(io.BytesIO(file_bytes))
                else:  # Excel
                    df = pd.read_excel(io.BytesIO(file_bytes))
                
                # Clean column names
                df.columns = [col.strip().replace(' ', '_').replace('-', '_').lower() for col in df.columns]
                
                # Generate table name from filename
                safe_filename = filename.split('.')[0].replace(' ', '_').replace('-', '_').lower()
                table_name = safe_filename
                
                # Ensure unique table name
                base_table_name = table_name
                counter = 1
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                while cursor.fetchone() is not None:
                    table_name = f"{base_table_name}_{counter}"
                    counter += 1
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                
                # Write to SQLite
                df.to_sql(table_name, conn, index=False, if_exists='replace')
                table_names_added.append(table_name)
                tables_info.append(f"{table_name} ({len(df)} rows)")
                
            except Exception as e:
                st.warning(f"⚠️ Skipped file '{filename}': {str(e)}")
                continue
        
        conn.commit()
        conn.close()
        
        if not table_names_added:
            return False, "No tables were added successfully", []
        
        message = f"✅ Added {len(table_names_added)} tables to database:\n" + "\n".join([f"  • {info}" for info in tables_info])
        
        return True, message, table_names_added
        
    except Exception as e:
        return False, f"Error adding tables: {str(e)}", []


def delete_table_from_sqlite(db_path: str, table_name: str) -> Tuple[bool, str]:
    """
    Delete a specific table from SQLite database
    
    Args:
        db_path: Path to database
        table_name: Name of table to delete
    
    Returns:
        (success, message)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if cursor.fetchone() is None:
            conn.close()
            return False, f"Table '{table_name}' not found"
        
        # Drop table
        cursor.execute(f"DROP TABLE {table_name}")
        conn.commit()
        conn.close()
        
        return True, f"✅ Table '{table_name}' deleted successfully"
        
    except Exception as e:
        return False, f"Error deleting table: {str(e)}"


def get_table_info_from_sqlite(db_path: str) -> Dict[str, Dict]:
    """
    Get detailed information about all tables in SQLite database
    
    Returns:
        Dict with table names as keys and info dicts as values
        Info includes: row_count, column_count, columns list
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        tables_info = {}
        
        for table in tables:
            # Get column info
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]
            
            tables_info[table] = {
                'row_count': row_count,
                'column_count': len(columns),
                'columns': columns
            }
        
        conn.close()
        return tables_info
        
    except Exception as e:
        st.error(f"Error getting table info: {e}")
        return {}


def create_persistent_sqlite_with_multiple_tables(
    files_data: List[Tuple[bytes, str]], 
    db_name: str,
    user_id: int
) -> Tuple[bool, Optional[str], str, List[str]]:
    """
    Create persistent SQLite database with multiple tables from multiple uploaded files
    
    Args:
        files_data: List of tuples (file_bytes, filename)
        db_name: Name for the database
        user_id: User ID
    
    Returns:
        (success, db_path, message, table_names)
    """
    try:
        # Generate unique file path for persistence (per user)
        safe_db_name = db_name.replace(' ', '_').replace('-', '_').lower()
        db_filename = f"{user_id}_{safe_db_name}.db"
        db_path = os.path.join(PERSISTENT_DB_DIR, db_filename)
        
        # Create SQLite connection to file (persistent)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        table_names = []
        tables_info = []
        
        # Process each file
        for file_bytes, filename in files_data:
            try:
                # Read file based on extension
                if filename.endswith('.csv'):
                    df = pd.read_csv(io.BytesIO(file_bytes))
                else:  # Excel
                    df = pd.read_excel(io.BytesIO(file_bytes))
                
                # Clean column names
                df.columns = [col.strip().replace(' ', '_').replace('-', '_').lower() for col in df.columns]
                
                # Generate table name from filename
                safe_filename = filename.split('.')[0].replace(' ', '_').replace('-', '_').lower()
                table_name = safe_filename
                
                # Ensure unique table name
                base_table_name = table_name
                counter = 1
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                while cursor.fetchone() is not None:
                    table_name = f"{base_table_name}_{counter}"
                    counter += 1
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                
                # Write to SQLite
                df.to_sql(table_name, conn, index=False, if_exists='replace')
                table_names.append(table_name)
                tables_info.append(f"{table_name} ({len(df)} rows)")
                
            except Exception as e:
                st.warning(f"⚠️ Skipped file '{filename}': {str(e)}")
                continue
        
        conn.commit()
        conn.close()
        
        if not table_names:
            return False, None, "No tables were created successfully", []
        
        message = f"✅ Database '{db_name}' created with {len(table_names)} tables:\n" + "\n".join([f"  • {info}" for info in tables_info])
        
        return True, db_path, message, table_names
        
    except Exception as e:
        return False, None, f"Database creation error: {str(e)}", []


def create_temp_database_from_mysql_file(file_bytes: bytes, filename: str, mysql_conn) -> Tuple[bool, Optional[str], str]:
    """Load uploaded file into custom MySQL database as a new table"""
    try:
        # Read file based on extension
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_bytes))
        else:  # Excel
            df = pd.read_excel(io.BytesIO(file_bytes))
       
        # Generate table name from filename
        safe_filename = filename.split('.')[0].replace(' ', '_').replace('-', '_').lower()
        table_name = safe_filename
       
        # Clean column names
        df.columns = [col.strip().replace(' ', '_').replace('-', '_') for col in df.columns]
       
        # Write to MySQL
        from sqlalchemy import create_engine
        engine = create_engine(f"mysql+mysqlconnector://{mysql_conn.user}:{mysql_conn.password}@{mysql_conn.host}:{mysql_conn.port}/{mysql_conn.database}")
        df.to_sql(table_name, engine, if_exists='replace', index=False)
       
        return True, table_name, f"Data loaded into custom MySQL table '{table_name}' ({len(df)} rows)"
    except Exception as e:
        return False, None, f"File processing error: {str(e)}"
