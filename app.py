"""
SQL Assistant Pro - Enhanced Version with Groq (Meta Llama)
Features:
1. Context Retention: Recent 5 messages + summarized older messages + 3 semantically similar Q&As
2. LLM-Based Smart Query Analysis
3. Enhanced Product Display with Interactive Cards
4. Improved Authentication UI
5. Delete Confirmation Dialogs
6. FIXED: SQLite compatibility for custom databases
7. NEW: Persistent Custom SQLite Databases (file-based)
8. NEW: Custom MySQL Database Connection Support
9. NEW: User-specific previous SQLite DB listing on login
10. NEW: UI-based credential input for Custom MySQL
11. FIXED: Improved Visualization Logic for Better Data Handling
12. FIXED: Generic Data Display (No Product Assumption)
13. FIXED: Dynamic Sample Data in Responses
DATABASE MIGRATION REQUIRED:
If you're updating from a previous version, run this SQL command on your auth database:
ALTER TABLE chat_history ADD COLUMN result_data LONGTEXT AFTER response;
This adds persistent storage for query results so users can view historical data.
"""
import streamlit as st
import mysql.connector
from mysql.connector import Error
import pandas as pd
import json
from datetime import datetime
import hashlib
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Tuple, Optional
from groq import Groq
import os
import io
import sqlite3
import base64
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import tempfile
import shutil
import glob

from db_chat_manager import (
    create_new_chat,
    get_user_chats,
    get_chat_history,
    save_chat_turn,
    rename_chat,
    delete_chat,
    generate_smart_chat_title
)

from response_engine import (
    generate_db_response_with_presentation,
    create_visualization_if_applicable,
    is_product_data,
    display_generic_row
)

from file_db_manager import (
    create_persistent_sqlite_with_multiple_tables,
    add_tables_to_existing_sqlite,
    delete_table_from_sqlite,
    get_table_info_from_sqlite,
    create_temp_database_from_mysql_file
)

from db_table_selector import (
    render_table_selector,
    get_selected_table_set
)


# ================= CONFIGURATION =================
st.set_page_config(
    page_title="SQL Assistant Pro",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded"
)
# Custom CSS for better UI
st.markdown("""
<style>
    /* Login/Signup Page Styling */
    .auth-container {
        max-width: 500px;
        margin: 0 auto;
        padding: 2rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
    }
   
    .auth-header {
        text-align: center;
        color: white;
        margin-bottom: 2rem;
    }
   
    .auth-form {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 5px 20px rgba(0,0,0,0.1);
    }
   
    /* Delete Confirmation Dialog */
    .delete-warning {
        background: #fff5f5;
        border: 2px solid #fc8181;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
   
    /* Sidebar Chat Items */
    .chat-item {
        border-radius: 10px;
        margin: 0.5rem 0;
        transition: all 0.3s ease;
    }
   
    .chat-item:hover {
        background: #f7fafc;
    }

    /* Custom DB Form Styling */
    .custom-db-form {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
    }

    /* DB List Styling */
    .db-item {
        background: #e6f3ff;
        padding: 0.5rem;
        border-radius: 5px;
        margin: 0.25rem 0;
    }

    /* Generic Data Row Display */
    .data-row-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #667eea;
    }
            
            /* Table management styling */
    .table-item {
        background: #f0f8ff;
        padding: 0.5rem;
        border-radius: 5px;
        margin: 0.25rem 0;
        border-left: 3px solid #4f46e5;
    }
    
    .table-item:hover {
        background: #e6f3ff;
    }
    
    /* Upload section */
    .upload-section {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border: 2px dashed #667eea;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Create persistent DB directory if it doesn't exist
PERSISTENT_DB_DIR = "custom_dbs"
os.makedirs(PERSISTENT_DB_DIR, exist_ok=True)

# SSL Certificate Path
try:
    ssl_ca_path = st.secrets.get("ssl_ca_path", None)
except:
    ssl_ca_path = None

# Load embedding model for semantic search (cached)
@st.cache_resource
def load_embedding_model():
    """Load sentence transformer model for semantic similarity"""
    return SentenceTransformer('all-MiniLM-L6-v2')

embedding_model = load_embedding_model()

# ================= SESSION STATE INITIALIZATION =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'current_chat_id' not in st.session_state:
    st.session_state.current_chat_id = None
if 'business_schema' not in st.session_state:
    st.session_state.business_schema = {}
if 'db_mode' not in st.session_state:
    st.session_state.db_mode = "system"  # system, custom_sqlite, custom_mysql
if 'active_custom_sqlite_path' not in st.session_state:
    st.session_state.active_custom_sqlite_path = None
if 'user_sqlite_dbs' not in st.session_state:
    st.session_state.user_sqlite_dbs = []  # List of user's DB paths
if 'custom_mysql_params' not in st.session_state:
    st.session_state.custom_mysql_params = {}  # Dict for MySQL creds
if 'custom_mysql_connection' not in st.session_state:
    st.session_state.custom_mysql_connection = None
if 'custom_schema' not in st.session_state:
    st.session_state.custom_schema = {}
if 'show_rename_dialog' not in st.session_state:
    st.session_state.show_rename_dialog = False
if 'rename_chat_id' not in st.session_state:
    st.session_state.rename_chat_id = None
if 'show_delete_dialog' not in st.session_state:
    st.session_state.show_delete_dialog = False
if 'delete_chat_id' not in st.session_state:
    st.session_state.delete_chat_id = None
if "selected_tables" not in st.session_state:
    st.session_state.selected_tables  = {
    "system": {
        "system_mysql": set()
    },
    "custom_mysql": {
        "host|db_name": set()
    },
    "custom_sqlite": {
        "absolute_db_path": set()
    }
}



def render_fixed_header(username: str):
    st.markdown(
        f"""
        <style>
        .fixed-header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 60px;
            background-color: #0e1117;
            border-bottom: 1px solid #333;
            z-index: 999;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 1.5rem;
            color: white;
        }}
        .app-content {{
            margin-top: 75px;
        }}
        </style>

        <div class="fixed-header">
            <div style="font-size: 1.2rem; font-weight: 600;">
                💬 Smart SQL Chat
            </div>
            <div>
                <span style="margin-right: 1rem;">👤 {username}</span>
            </div>
        </div>
        <div class="app-content">
        """,
        unsafe_allow_html=True
    )


# ================= UTILITY FUNCTIONS =================
def load_user_sqlite_dbs(user_id: int) -> List[str]:
    """Load list of user's persistent SQLite DB paths"""
    pattern = os.path.join(PERSISTENT_DB_DIR, f"{user_id}_*.db")
    db_files = glob.glob(pattern)
    # Sort by modification time, newest first
    db_files.sort(key=os.path.getmtime, reverse=True)
    return db_files

# ================= DATABASE CONNECTION FUNCTIONS =================

def get_temp_ssl_ca(ca_b64_secret: str) -> str:
    """Decode base64 SSL CA and write to temp file."""
    if not ca_b64_secret:
        return ""
    try:
        cert_bytes = base64.b64decode(ca_b64_secret)
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as temp_file:
            temp_file.write(cert_bytes)
            temp_path = temp_file.name
        return temp_path  # Path to temp cert file
    except Exception as e:
        st.error(f"Failed to decode SSL cert: {e}")
        return ""

ssl_ca_b64 = st.secrets["database"].get("ssl_ca_b64", "")
ssl_ca_path = get_temp_ssl_ca(ssl_ca_b64)

def get_auth_db_connection():
    """Connect to authentication database"""
    try:
        if "auth_database" in st.secrets:
            # Use provided SSL config, with option for ssl_disabled
            ssl_config = {
                'ssl_disabled': st.secrets["auth_database"].get("ssl_disabled", False),
                'ssl_verify_cert': not st.secrets["auth_database"].get("ssl_disabled", False),
                # 'ssl_ca': st.secrets["auth_database"].get("ssl_ca", ""),
                'ssl_ca': ssl_ca_path,
                'ssl_verify_identity': not st.secrets["auth_database"].get("ssl_disabled", False),
            }
            connection = mysql.connector.connect(
                host=st.secrets["auth_database"]["host"],
                port=int(st.secrets["auth_database"]["port"]),
                database=st.secrets["auth_database"]["database"],
                user=st.secrets["auth_database"]["user"],
                password=st.secrets["auth_database"]["password"],
                connect_timeout=30,
                **ssl_config
            )
        else:
            connection = mysql.connector.connect(
                host='localhost',
                database='auth_db',
                user='root',
                password='password',
                connect_timeout=10,
                ssl_disabled=True  # Default to disabled for local
            )
       
        if connection.is_connected():
            init_auth_tables(connection)
        return connection
    except Error as e:
        st.error(f"❌ Auth Database connection failed: {e}")
        return None

def get_business_db_connection():
    """Connect to business database"""
    try:
        if "database" in st.secrets:
            # Use provided SSL config, with option for ssl_disabled
            ssl_config = {
                'ssl_disabled': st.secrets["database"].get("ssl_disabled", False),
                'ssl_verify_cert': not st.secrets["database"].get("ssl_disabled", False),
                # 'ssl_ca': st.secrets["database"].get("ssl_ca", ""),
                'ssl_ca': ssl_ca_path,
                'ssl_verify_identity': not st.secrets["database"].get("ssl_disabled", False),
            }
            connection = mysql.connector.connect(
                host=st.secrets["database"]["host"],
                port=int(st.secrets["database"]["port"]),
                database=st.secrets["database"]["database"],
                user=st.secrets["database"]["user"],
                password=st.secrets["database"]["password"],
                connect_timeout=30,
                **ssl_config
            )
        else:
            connection = mysql.connector.connect(
                host='localhost',
                database='myntra_db',
                user='root',
                password='password',
                connect_timeout=10,
                ssl_disabled=True  # Default to disabled for local
            )
        return connection
    except Error as e:
        st.error(f"❌ Business Database connection failed: {e}")
        return None

def get_custom_mysql_connection_from_params(params: Dict) -> Optional[mysql.connector.connection.MySQLConnection]:
    """Connect to custom MySQL using provided params"""
    try:
        ssl_config = {
            'ssl_disabled': params.get("ssl_disabled", True),
            'ssl_verify_cert': not params.get("ssl_disabled", True),
            # 'ssl_ca': params.get("ssl_ca", ""),
            'ssl_ca': ssl_ca_path,
            'ssl_verify_identity': not params.get("ssl_disabled", True),
        }
        connection = mysql.connector.connect(
            host=params["host"],
            port=int(params["port"]),
            database=params["database"],
            user=params["user"],
            password=params["password"],
            connect_timeout=30,
            **ssl_config
        )
        return connection
    except Error as e:
        st.error(f"❌ Custom MySQL connection failed: {e}")
        return None

def init_auth_tables(connection):
    """Initialize authentication tables if they don't exist"""
    cursor = connection.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(64) NOT NULL,
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
       
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                mode VARCHAR(20) NOT NULL DEFAULT 'database',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
       
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                history_id INT AUTO_INCREMENT PRIMARY KEY,
                chat_id INT NOT NULL,
                user_id INT NOT NULL,
                question TEXT,
                query_generated TEXT,
                response TEXT,
                result_data LONGTEXT,
                mode VARCHAR(20),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
            )
        """)
       
        connection.commit()
    except Error as e:
        st.error(f"Error initializing auth tables: {e}")
    finally:
        cursor.close()




# ================= AUTHENTICATION FUNCTIONS =================
def hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username: str, password: str) -> Tuple[bool, str]:
    """Create new user"""
    connection = get_auth_db_connection()
    if not connection:
        return False, "Database connection failed"
   
    try:
        cursor = connection.cursor()
        hashed_pw = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, hashed_pw)
        )
        connection.commit()
        return True, "User created successfully"
    except Error as e:
        if "Duplicate entry" in str(e):
            return False, "Username already exists"
        return False, f"Error: {e}"
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def verify_user(username: str, password: str) -> Tuple[bool, Optional[int]]:
    """Verify user credentials"""
    connection = get_auth_db_connection()
    if not connection:
        return False, None
   
    try:
        cursor = connection.cursor()
        hashed_pw = hash_password(password)
        cursor.execute(
            "SELECT user_id FROM users WHERE username = %s AND password_hash = %s",
            (username, hashed_pw)
        )
        result = cursor.fetchone()
       
        if result:
            return True, result[0]
        return False, None
    except Error as e:
        st.error(f"Login error: {e}")
        return False, None
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

# ================= DATABASE SCHEMA FUNCTIONS =================
def is_sqlite_connection(connection) -> bool:
    """Check if connection is SQLite"""
    return isinstance(connection, sqlite3.Connection)

def get_database_schema(connection, table_name: Optional[str] = None) -> Dict:
    """Get comprehensive database schema with relationships - works with both MySQL and SQLite"""
    schema = {}
    cursor = None
    is_sqlite = is_sqlite_connection(connection)
   
    try:
        cursor = connection.cursor()
       
        # Get all tables or specific table
        if table_name:
            tables = [table_name]
        else:
            if is_sqlite:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [table[0] for table in cursor.fetchall()]
            else:
                cursor.execute("SHOW TABLES")
                tables = [table[0] for table in cursor.fetchall()]
       
        for table in tables:
            columns = []
           
            # Get columns - different syntax for SQLite vs MySQL
            if is_sqlite:
                # SQLite uses PRAGMA table_info
                cursor.execute(f"PRAGMA table_info({table})")
                for col in cursor.fetchall():
                    # SQLite PRAGMA returns: cid, name, type, notnull, dflt_value, pk
                    columns.append({
                        'name': col[1],
                        'type': col[2],
                        'null': 'NO' if col[3] else 'YES',
                        'key': 'PRI' if col[5] else '',
                        'default': col[4],
                        'extra': ''
                    })
            else:
                # MySQL uses DESCRIBE
                cursor.execute(f"DESCRIBE {table}")
                for col in cursor.fetchall():
                    columns.append({
                        'name': col[0],
                        'type': col[1],
                        'null': col[2],
                        'key': col[3],
                        'default': col[4],
                        'extra': col[5]
                    })
           
            # Get foreign key relationships
            relationships = []
            if is_sqlite:
                # SQLite uses PRAGMA foreign_key_list
                cursor.execute(f"PRAGMA foreign_key_list({table})")
                for rel in cursor.fetchall():
                    # SQLite PRAGMA returns: id, seq, table, from, to, on_update, on_delete, match
                    relationships.append({
                        'column': rel[3],
                        'references_table': rel[2],
                        'references_column': rel[4]
                    })
            else:
                # MySQL uses INFORMATION_SCHEMA
                cursor.execute(f"""
                    SELECT
                        COLUMN_NAME,
                        REFERENCED_TABLE_NAME,
                        REFERENCED_COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = '{table}'
                    AND REFERENCED_TABLE_NAME IS NOT NULL
                """)
                for rel in cursor.fetchall():
                    relationships.append({
                        'column': rel[0],
                        'references_table': rel[1],
                        'references_column': rel[2]
                    })
           
            # Get sample data (first 3 rows)
            cursor.execute(f"SELECT * FROM {table} LIMIT 3")
            sample_data = cursor.fetchall()
           
            schema[table] = {
                'columns': columns,
                'relationships': relationships,
                'sample_data': sample_data
            }
       
        return schema
    except Exception as e:
        st.error(f"Schema fetch error: {e}")
        return {}
    finally:
        if cursor:
            cursor.close()


def get_filtered_schema(schema: dict) -> dict:
    selected = st.session_state.get("selected_tables", set())

    if not selected:
        return {}

    filtered = {
        table: schema[table]
        for table in selected
        if table in schema
    }

    return filtered

def get_filtered_schema_for_active_db(full_schema: dict) -> dict:
    """
    Returns schema filtered by user-selected tables
    for the currently active database.
    """

    db_mode = st.session_state.db_mode

    # 🔑 Identify database ID
    if db_mode == "custom_sqlite":
        db_id = st.session_state.get("active_custom_sqlite_path")
    elif db_mode == "custom_mysql":
        p = st.session_state.get("custom_mysql_params", {})
        db_id = f"{p.get('host')}|{p.get('database')}"
    else:
        db_id = "system_mysql"

    selected_tables = (
        st.session_state.selected_tables
        .get(db_mode, {})
        .get(db_id, set())
    )

    # 🔒 Filter schema
    return {
        table: full_schema[table]
        for table in selected_tables
        if table in full_schema
    }


def format_schema_for_llm(schema: Dict, tables_to_include: Optional[List[str]] = None) -> str:
    """Format schema for LLM"""
    schema_text = "DATABASE SCHEMA:\n\n"
   
    # Filter tables if specified
    if tables_to_include:
        filtered_schema = {k: v for k, v in schema.items() if k in tables_to_include}
    else:
        filtered_schema = schema
   
    for table_name, table_info in filtered_schema.items():
        schema_text += f"TABLE: {table_name}\n"
        schema_text += "Columns:\n"
        for col in table_info['columns']:
            key_info = f" [{col['key']}]" if col['key'] else ""
            null_info = " (nullable)" if col['null'] == 'YES' else " (required)"
            schema_text += f" - {col['name']}: {col['type']}{key_info}{null_info}\n"
       
        if table_info.get('relationships'):
            schema_text += "\nRelationships:\n"
            for rel in table_info['relationships']:
                schema_text += f" - {rel['column']} → {rel['references_table']}.{rel['references_column']}\n"
       
        if table_info.get('sample_data'):
            schema_text += f"\nSample Data ({len(table_info['sample_data'])} rows):\n"
            col_names = [col['name'] for col in table_info['columns']]
            for row in table_info['sample_data'][:3]:
                row_dict = dict(zip(col_names, row))
                schema_text += f" {row_dict}\n"
       
        schema_text += "\n" + "="*80 + "\n\n"
   
    # Add relationship summary for multi-table queries
    if len(filtered_schema) > 1:
        schema_text += "RELATIONSHIP SUMMARY:\n"
        for table_name, table_info in filtered_schema.items():
            if table_info.get('relationships'):
                for rel in table_info['relationships']:
                    schema_text += f" {table_name}.{rel['column']} → {rel['references_table']}.{rel['references_column']}\n"
        schema_text += "\n"
   
    return schema_text

# ================= CONTEXT MANAGEMENT FUNCTIONS =================
def compute_embedding(text: str) -> np.ndarray:
    """Compute embedding for text using sentence transformer"""
    return embedding_model.encode(text)

def find_semantically_similar_messages(
    current_question: str,
    chat_history: List[Dict],
    top_k: int = 3
) -> List[Dict]:
    """Find top-k semantically similar Q&A pairs from chat history"""
    if not chat_history:
        return []
   
    # Compute embedding for current question
    current_embedding = compute_embedding(current_question)
   
    # Compute embeddings for all historical questions
    similarities = []
    for turn in chat_history:
        question_embedding = compute_embedding(turn['question'])
        similarity = cosine_similarity(
            current_embedding.reshape(1, -1),
            question_embedding.reshape(1, -1)
        )[0][0]
        similarities.append((similarity, turn))
   
    # Sort by similarity and get top-k
    similarities.sort(key=lambda x: x[0], reverse=True)
    return [turn for _, turn in similarities[:top_k]]

def summarize_old_messages(messages: List[Dict]) -> str:
    """Summarize older messages using Groq Llama"""
    if not messages:
        return ""
   
    # Prepare summary request
    summary_text = "Previous conversation summary:\n"
    for msg in messages:
        response_preview = msg.get('response', '')[:200] if msg.get('response') else ''
        summary_text += f"Q: {msg['question']}\nA: {response_preview}...\n\n"
   
    try:
        client = Groq(api_key=st.secrets["groq"]["api_key"])
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": f"Summarize this conversation history concisely, focusing on key context and user preferences:\n\n{summary_text}"
            }],
            max_tokens=500,
            temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        st.warning(f"Summarization failed: {e}")
        return "Previous conversation context available but not summarized."

def build_optimized_context(
    chat_history: List[Dict],
    current_question: str,
    recent_count: int = 5,
    semantic_count: int = 3
) -> Tuple[str, Dict]:
    """
    Build optimized context with:
    1. Recent 5 messages (as is)
    2. Summary of older messages
    3. 3 semantically similar Q&As
    """
    context_parts = []
    stats = {
        'total_messages': len(chat_history),
        'recent_count': 0,
        'summarized_count': 0,
        'semantic_count': 0
    }
   
    if not chat_history:
        return "", stats
   
    # 1. Recent messages (last 5)
    recent_messages = chat_history[-recent_count:] if len(chat_history) >= recent_count else chat_history
    stats['recent_count'] = len(recent_messages)
   
    if recent_messages:
        context_parts.append("RECENT CONVERSATION (Last 5 messages):")
        for turn in recent_messages:
            context_parts.append(f"User: {turn['question']}")
            if turn.get('response'):
                context_parts.append(f"Assistant: {turn['response']}")
            if turn.get('query_generated'):
                context_parts.append(f"SQL: {turn['query_generated']}")
        context_parts.append("")
   
    # 2. Summary of older messages
    older_messages = chat_history[:-recent_count] if len(chat_history) > recent_count else []
    stats['summarized_count'] = len(older_messages)
   
    if older_messages:
        summary = summarize_old_messages(older_messages)
        if summary:
            context_parts.append("EARLIER CONVERSATION SUMMARY:")
            context_parts.append(summary)
            context_parts.append("")
   
    # 3. Semantically similar messages (excluding recent ones)
    older_for_semantic = chat_history[:-recent_count] if len(chat_history) > recent_count else []
    similar_messages = find_semantically_similar_messages(
        current_question,
        older_for_semantic,
        top_k=semantic_count
    )
    stats['semantic_count'] = len(similar_messages)
   
    if similar_messages:
        context_parts.append("RELEVANT SIMILAR CONVERSATIONS:")
        for i, turn in enumerate(similar_messages, 1):
            context_parts.append(f"{i}. User: {turn['question']}")
            response_preview = turn.get('response', '')[:150] if turn.get('response') else ''
            context_parts.append(f" Assistant: {response_preview}...")
            if turn.get('query_generated'):
                context_parts.append(f" SQL: {turn['query_generated']}")
        context_parts.append("")
   
    context = "\n".join(context_parts)
    return context, stats

# ================= LLM-BASED QUERY INTENT ANALYSIS =================
def analyze_query_intent_with_llm(question: str, schema: Dict) -> Dict:
    """Use LLM to analyze query intent and determine table requirements"""
    try:
        client = Groq(api_key=st.secrets["groq"]["api_key"])
       
        # Prepare schema summary for LLM
        schema_summary = "Available Tables:\n"
        for table_name, table_info in schema.items():
            columns = [col['name'] for col in table_info['columns']]
            schema_summary += f"- {table_name}: {', '.join(columns)}\n"
            if table_info.get('relationships'):
                for rel in table_info['relationships']:
                    schema_summary += f" → {rel['column']} links to {rel['references_table']}.{rel['references_column']}\n"
       
        analysis_prompt = f"""Analyze this database query intent:
{schema_summary}
User Question: "{question}"
Determine:
1. Which tables are needed to answer this question?
2. Does it require a JOIN between tables, or can it be answered from a single table?
3. What is the query type (single_table, multi_table, aggregation, etc.)?
Return your analysis in this JSON format:
{{
    "requires_join": true/false,
    "tables_needed": ["table1", "table2"],
    "intent_type": "single_table" or "multi_table",
    "reasoning": "Brief explanation of your analysis"
}}
IMPORTANT: Prefer single-table queries when possible for better performance. Only use JOIN when data from multiple tables is absolutely necessary.
Return ONLY the JSON, no additional text."""
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": analysis_prompt
            }],
            max_tokens=500,
            temperature=0.1
        )
       
        # Parse response
        result = response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        result = result.replace('```json', '').replace('```', '').strip()
       
        analysis = json.loads(result)
       
        # Validate and return
        return {
            'requires_join': analysis.get('requires_join', False),
            'tables_needed': analysis.get('tables_needed', list(schema.keys())),
            'intent_type': analysis.get('intent_type', 'unknown'),
            'reasoning': analysis.get('reasoning', 'LLM analysis completed')
        }
       
    except Exception as e:
        st.warning(f"LLM intent analysis failed, using fallback: {e}")
        # Fallback: use all tables
        return {
            'requires_join': False,
            'tables_needed': list(schema.keys()),
            'intent_type': 'unknown',
            'reasoning': 'Fallback analysis - using all available tables'
        }

# ================= SMART QUERY GENERATION =================
def generate_sql_query(question: str, schema_text: str, context: str, intent_analysis: Optional[Dict] = None, is_sqlite: bool = False, user_prompt_override: str = "") -> Dict:
    """Generate SQL query using Groq Llama with smart multi-table logic"""
    try:
        client = Groq(api_key=st.secrets["groq"]["api_key"])
       
        # Determine SQL dialect
        sql_dialect = "SQLite" if is_sqlite else "MySQL"
       
        # Enhanced system prompt for smart querying
        system_prompt = f"""
You are a senior SQL engineer and database analyst.
Your task is to generate a SINGLE, correct, optimized {sql_dialect} SELECT query.

========================
CORE RESPONSIBILITIES
========================
1. Correctly understand the user's intent
2. Decide whether the query needs:
   - MULTIPLE tables (ONLY if required)
3. Produce a clean, efficient SQL query using ONLY the provided schema

========================
MULTI-TABLE DECISION RULES (VERY IMPORTANT)
========================
- FIRST assume the question can be answered using a SINGLE table
- Use JOINs ONLY when:
  a) Data is clearly required from more than one table
  b) The question explicitly combines different domains (e.g. products + sales)
- NEVER use unnecessary JOINs
- NEVER hallucinate tables or columns
- Analyse schema and sample data clearly for correct query generation

========================
CONTEXT & CONVERSATION INTELLIGENCE
========================
You MUST analyze the conversation context and classify the question as ONE of these:

1. CONTEXT RESET
   - New product/category/domain
   - Ignore all previous filters

2. REFINEMENT
   - Adds or narrows filters (color, size, brand, price, etc.)
   - Combine ALL previous filters with the new ones

3. ANALYTICAL
   - Aggregations like total sales, revenue, best-selling, counts
   - Apply filters first, THEN aggregate

========================
REFINEMENT LOGIC (MANDATORY)
========================
- NEVER drop previous filters unless context reset is detected
- Always accumulate filters using AND
- Examples:
  User: "I want kurti"
  → WHERE category = 'kurti'

  User: "pink"
  → WHERE category = 'kurti' AND color = 'pink'

  User: "M size"
  → WHERE category = 'kurti' AND color = 'pink' AND size = 'M'

  User: "show me shoes"
  → CONTEXT RESET
  → WHERE category = 'shoes'

========================
PRODUCT INTELLIGENCE RULES
========================
Use common-sense product knowledge when interpreting queries:

- "kids shoes" → filter size < 6 OR description contains 'kids'
- "summer shoes" → description contains sandals, flip-flops, sliders
- "party wear" → premium, designer, embellished keywords
- If unsure, prefer description-based filtering using LIKE

========================
QUERY CONSTRUCTION RULES
========================
- Use ONLY columns that exist in the schema
- Always use WHERE for filters
- Use DISTINCT when JOINs may cause duplication
- Always use table aliases in multi-table queries
- Use ORDER BY when ranking or sorting makes sense
- Use LIMIT 10–15 to avoid large outputs
- Optimize for readability AND performance

========================
STRICT OUTPUT RULES (NON-NEGOTIABLE)
========================
- Output ONLY a valid {sql_dialect} SELECT query
- NO explanations
- NO markdown
- NO comments
- NO extra text before or after the query
"""

        user_prompt = f"""
        CONVERSATION CONTEXT:
        {context}

        CURRENT QUESTION:
        {question}
        """
                
        
        # 🔥 User-adjustable guidance
        if user_prompt_override:
            user_prompt += f"""
                USER INSTRUCTIONS (IMPORTANT):
                {user_prompt_override}
                """
        else:
            # Build user prompt with context and schema
            user_prompt += """
                Generate the optimal SQL query following all the rules above.
                IMPORTANT:
                - If this is a refinement, include ALL accumulated filters in WHERE clause
                - If analytical, use appropriate aggregate functions
                - Return ONLY the SQL query, no explanations."""

        print("user prompt -> ",user_prompt)

       
        # Add intent analysis if available
        if intent_analysis:
            user_prompt += f"""
QUERY ANALYSIS (from LLM):
Intent Type: {intent_analysis['intent_type']}
Requires JOIN: {intent_analysis['requires_join']}
Tables Needed: {', '.join(intent_analysis['tables_needed'])}
Reasoning: {intent_analysis['reasoning']}
"""
       
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1000,
            temperature=0.1
        )
       
        query = response.choices[0].message.content.strip()
       
        # Clean up query - remove markdown code blocks if present
        query = query.replace('```sql', '').replace('```', '').strip()
       
        # Remove any explanatory text before or after the query
        lines = query.split('\n')
        sql_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('--'):
                sql_lines.append(line)
       
        query = ' '.join(sql_lines)
       
        # Validate query
        if not query.upper().startswith('SELECT'):
            return {
                "success": False,
                "error": "Generated query is not a SELECT statement",
                "query": query
            }
        
        usage = response.usage
       
        return {
            "success": True,
            "query": query,
            "intent": intent_analysis['intent_type'] if intent_analysis else 'unknown',
            "debug": {
                "full_schema": schema_text,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "user_prompt_override": user_prompt_override
            },
            "tokens": {
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0
            }
        }
       
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": None
        }

def execute_query(connection, query: str) -> Dict:
    """Execute SQL query and return results - works with both MySQL and SQLite"""
    cursor = None
    is_sqlite = is_sqlite_connection(connection)
   
    try:
        cursor = connection.cursor()
        cursor.execute(query)
       
        # Get column names
        columns = [desc[0] for desc in cursor.description]
       
        results = cursor.fetchall()
        df = pd.DataFrame(results, columns=columns)
       
        return {
            "success": True,
            "data": df,
            "row_count": len(df)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }
    finally:
        if cursor:
            cursor.close()


# ================= UI HELPER FUNCTIONS =================
def create_copy_button(text: str, label: str = "Copy") -> str:
    """Create copy-to-clipboard button"""
    escaped_text = text.replace('`', '\\`').replace('$', '\\$').replace('"', '\\"')
    return f"""
    <button onclick="navigator.clipboard.writeText(`{escaped_text}`)" style="
        background: #667eea;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        cursor: pointer;
        font-size: 0.9rem;
        margin: 0.5rem 0;
    ">{label}</button>
    """

def create_download_link(df: pd.DataFrame, filename: str) -> str:
    """Create download link for DataFrame"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f"""
    <a href="data:file/csv;base64,{b64}" download="{filename}" style="
        background: #48bb78;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        text-decoration: none;
        display: inline-block;
        margin: 0.5rem 0;
    ">📥 Download CSV</a>
    """

def display_product_dropdown(product: Dict, idx: int, turn_idx: int = 0):
    """Display product in expandable dropdown - Only for confirmed product data"""
    name = product.get('product_name') or product.get('name', 'Unknown Product')
    price = product.get('price') or product.get('selling_price', 0) or product.get('mrp', 0)
   
    # Get additional quick info for the header
    brand = product.get('brand', '')
    category = product.get('category', '')
   
    # Create header text
    header_text = f"🛍️ {name} - ₹{price:,.2f}"
    if brand:
        header_text += f" | {brand}"
    if category:
        header_text += f" | {category}"
   
    # Create unique key for expander
    expander_key = f"product_exp_{turn_idx}_{idx}"
   
    with st.expander(header_text, expanded=False):
        # Display product details in organized sections
        col1, col2 = st.columns(2)
       
        with col1:
            st.markdown("### 💰 Price Information")
            st.markdown(f"**Price:** ₹{price:,.2f}")
            if 'mrp' in product and product['mrp']:
                st.markdown(f"**MRP:** ₹{product['mrp']:,.2f}")
            if 'discount' in product and product['discount']:
                st.markdown(f"**Discount:** {product['discount']}%")
           
            st.markdown("### 📦 Product Details")
            if brand:
                st.markdown(f"**Brand:** {brand}")
            if category:
                st.markdown(f"**Category:** {category}")
            if 'color' in product and product['color']:
                st.markdown(f"**Color:** {product['color']}")
            if 'size' in product and product['size']:
                st.markdown(f"**Size:** {product['size']}")
       
        with col2:
            st.markdown("### ℹ️ Additional Information")
            if 'material' in product and product['material']:
                st.markdown(f"**Material:** {product['material']}")
            if 'stock' in product and product['stock'] is not None:
                stock_status = "✅ In Stock" if product['stock'] > 0 else "❌ Out of Stock"
                st.markdown(f"**Stock:** {stock_status} ({product['stock']} units)")
            if 'rating' in product and product['rating']:
                stars = '⭐' * int(float(product['rating']))
                st.markdown(f"**Rating:** {stars} ({product['rating']})")
            if 'reviews' in product and product['reviews']:
                st.markdown(f"**Reviews:** {product['reviews']}")
       
        # Show all other attributes
        st.markdown("### 📋 All Attributes")
       
        # Collect all attributes not already displayed
        displayed_keys = ['product_name', 'name', 'price', 'selling_price', 'mrp', 'discount',
                         'brand', 'category', 'color', 'size', 'material', 'stock', 'rating', 'reviews']
       
        other_attrs = {k: v for k, v in product.items() if k not in displayed_keys and v is not None and v != ''}
       
        if other_attrs:
            for key, value in other_attrs.items():
                st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")
        else:
            st.caption("No additional attributes")

# ================= LOAD BUSINESS DATABASE SCHEMA =================
@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_business_schema():
    """Load and cache business database schema"""
    connection = get_business_db_connection()
    if connection:
        try:
            schema = get_database_schema(connection)
            return schema
        finally:
            if connection.is_connected():
                connection.close()
    return {}

# Initialize business schema on app load
if not st.session_state.business_schema:
    st.session_state.business_schema = load_business_schema()

def render_assistant_response(
    *,
    summary: str,
    df=None,
    visualization=None,
    query: str = None,
    intent_analysis: dict = None,
    context_stats: dict = None,
    llm_meta: dict = None,
    is_sqlite: bool = False,
    message_key: str = None
):
    """
    UX-optimized renderer with improved card-based UI
    Displays insights instead of raw tables
    """

    tabs = st.tabs([
        "📝 Answer | 📊 Data",
        "📈 Chart",
        "🧠 Query",
        "🧪 Debug"
    ])

    # ======================================================
    # 📝 ANSWER + DATA
    # ======================================================
    with tabs[0]:
        # ------------------ Answer ------------------
        st.markdown("## 📝 Answer")
        st.markdown(
            f"<div style='font-size:16px; line-height:1.6'>{summary}</div>",
            unsafe_allow_html=True
        )

        if llm_meta and llm_meta.get("tokens"):
            # st.caption(
            #     f"🧠 Tokens — "
            #     f"In: {llm_meta.get('input_tokens')} | "
            #     f"Out: {llm_meta.get('output_tokens')} | "
            #     f"Total: {llm_meta.get('total_tokens')}"
            # )
            st.caption(
                f"🧠 Tokens — "
                f"In: {llm_meta.get('tokens')} "
            )

        st.divider()

        # ------------------ Supporting Data ------------------
        # st.markdown("## 📊 Supporting Data")

        if df is not None and not df.empty:
            row_count = len(df)
            col_count = len(df.columns)

            # 🔹 High level overview
            # st.markdown(
            #     f"**This answer is derived from `{row_count}` records across `{col_count}` fields.**"
            # )

            # 🔹 Sample records (IMPROVED CARDS)
            st.markdown("### 🗂 Sample Records")
            sample_df = df.head(6)  # show up to 6 cards
            
            # Determine key columns to display prominently (first 3)
            key_cols = sample_df.columns[:min(3, len(sample_df.columns))].tolist()
            
            # Create grid: 2 cards per row
            num_cols = 2
            rows = [sample_df.iloc[i:i + num_cols] for i in range(0, len(sample_df), num_cols)]

            for row_df in rows:
                cols = st.columns(num_cols)
                
                for col_ui, (record_idx, row) in zip(cols, row_df.iterrows()):
                    with col_ui:
                        # Card container with styled border
                        with st.container():
                            # Header with colored accent border
                            header_value = str(row[key_cols[0]]) if len(key_cols) > 0 else f"Record {record_idx}"
                            
                            st.markdown(
                                f"""
                                <div style='
                                    border-left: 4px solid #1f77b4;
                                    padding-left: 12px;
                                    margin-bottom: 12px;
                                    background: linear-gradient(90deg, rgba(31, 119, 180, 0.05) 0%, rgba(255, 255, 255, 0) 100%);
                                    padding-top: 8px;
                                    padding-bottom: 8px;
                                    border-radius: 0 4px 4px 0;
                                '>
                                    <div style='font-weight: 600; font-size: 1.05rem; color: #1f77b4; margin-bottom: 4px;'>
                                        {header_value}
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
                            
                            # Display key info prominently (remaining key columns)
                            if len(key_cols) > 1:
                                for col in key_cols[1:]:
                                    col_value = row[col]
                                    # Format based on type
                                    if isinstance(col_value, (int, float)):
                                        if isinstance(col_value, float):
                                            display_value = f"{col_value:,.2f}"
                                        else:
                                            display_value = f"{col_value:,}"
                                    else:
                                        display_value = str(col_value)
                                    
                                    st.markdown(
                                        f"<div style='margin-bottom: 6px;'>"
                                        f"<span style='color: #666; font-size: 0.9rem;'>{col}:</span> "
                                        f"<span style='font-weight: 500;'>{display_value}</span>"
                                        f"</div>",
                                        unsafe_allow_html=True
                                    )
                            
                            # Expandable section for all other fields
                            remaining_cols = [c for c in row.index if c not in key_cols]
                            
                            if remaining_cols:
                                with st.expander(f"📋 View all {len(row)} fields"):
                                    # Display all fields in a clean format
                                    for col in row.index:
                                        col_value = row[col]
                                        # Format based on type
                                        if isinstance(col_value, (int, float)):
                                            if isinstance(col_value, float):
                                                display_value = f"{col_value:,.2f}"
                                            else:
                                                display_value = f"{col_value:,}"
                                        else:
                                            display_value = str(col_value)
                                        
                                        st.markdown(f"**{col}:** {display_value}")
                            else:
                                # If only key columns exist, show them all in expander
                                with st.expander(f"📋 View all {len(row)} fields"):
                                    for col, val in row.items():
                                        st.markdown(f"**{col}:** {val}")
                        
                        # Add spacing between cards vertically
                        st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

            # 🔹 Raw data hidden in collapsible section
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("📁 View full dataset (advanced)"):
                st.dataframe(df, use_container_width=True)

                csv_name = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                st.download_button(
                    "⬇️ Download CSV",
                    df.to_csv(index=False),
                    file_name=csv_name,
                    mime="text/csv",
                    key=f"download_{message_key}"
                )
        else:
            st.info("This answer did not require structured data output.")

    # ======================================================
    # 📈 CHART TAB
    # ======================================================
    with tabs[1]:
        if visualization:
            st.markdown("## 📈 Visual Summary")
            st.caption("This chart highlights the most relevant trend.")
            st.plotly_chart(visualization, use_container_width=True)
        else:
            st.info("No visualization generated.")

    # ======================================================
    # 🧠 QUERY TAB
    # ======================================================
    with tabs[2]:
        if query:
            st.caption(f"Database: {'SQLite' if is_sqlite else 'MySQL'}")
            st.code(query, language="sql")
        else:
            st.info("No SQL query available.")

        if intent_analysis:
            st.divider()
            st.markdown("### 🎯 Query Intent")
            st.json(intent_analysis)

    # ======================================================
    # 🧪 DEBUG TAB
    # ======================================================
    with tabs[3]:
        
        if context_stats:
            st.markdown("### 📊 Context Stats")
            st.json(context_stats)

        if llm_meta and llm_meta.get("prompt"):
            st.divider()
            st.markdown("### 🧠 LLM Prompt")
            st.text_area(
                "Prompt",
                llm_meta["prompt"],
                height=300,
                key=f"prompt_{message_key}"
            )
        
        if llm_meta and llm_meta.get("tokens"):
            # st.caption(
            #     f"🧠 Tokens — "
            #     f"In: {llm_meta.get('input_tokens')} | "
            #     f"Out: {llm_meta.get('output_tokens')} | "
            #     f"Total: {llm_meta.get('total_tokens')}"
            # )
            st.caption(
                f"🧠 Tokens — "
                f"In: {llm_meta.get('tokens')} "
            )

        if not context_stats and not llm_meta:
            st.info("No debug info available.")

# ================= MAIN APPLICATION =================
# ================= LOGIN/SIGNUP =================
if not st.session_state.logged_in:
    # Center the auth container
    col1, col2, col3 = st.columns([1, 2, 1])
   
    with col2:
        # st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        st.markdown('<div class="auth-header">', unsafe_allow_html=True)
        st.markdown("# 🗄️ SQL Assistant Pro")
        st.markdown("### Powered by Meta Llama 3.3 via Groq")
        st.markdown('</div>', unsafe_allow_html=True)
       
        tab1, tab2 = st.tabs(["🔑 Login", "✨ Sign Up"])
       
        with tab1:
            # st.markdown('<div class="auth-form">', unsafe_allow_html=True)
            with st.form("login_form"):
                st.markdown("### Welcome Back!")
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password", placeholder="Enter your password")
               
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    submit = st.form_submit_button("Login", use_container_width=True, type="primary")
               
                if submit:
                    if username and password:
                        success, user_id = verify_user(username, password)
                        if success:
                            st.session_state.logged_in = True
                            st.session_state.user_id = user_id
                            st.session_state.username = username
                            # Load user's previous SQLite DBs
                            st.session_state.user_sqlite_dbs = load_user_sqlite_dbs(user_id)
                            st.success("✅ Login successful!")
                            st.rerun()
                        else:
                            st.error("❌ Invalid credentials")
                    else:
                        st.warning("⚠️ Please fill all fields")
            st.markdown('</div>', unsafe_allow_html=True)
       
        with tab2:
            st.markdown('<div class="auth-form">', unsafe_allow_html=True)
            with st.form("signup_form"):
                st.markdown("### Create Account")
                new_username = st.text_input("Username", placeholder="Choose a username")
                new_password = st.text_input("Password", type="password", placeholder="Choose a password")
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm your password")
               
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    submit = st.form_submit_button("Sign Up", use_container_width=True, type="primary")
               
                if submit:
                    if new_username and new_password and confirm_password:
                        if new_password == confirm_password:
                            if len(new_password) >= 6:
                                success, message = create_user(new_username, new_password)
                                if success:
                                    st.success(f"✅ {message}")
                                    st.info("👉 Please login with your credentials")
                                else:
                                    st.error(f"❌ {message}")
                            else:
                                st.error("❌ Password must be at least 6 characters")
                        else:
                            st.error("❌ Passwords do not match")
                    else:
                        st.warning("⚠️ Please fill all fields")
            st.markdown('</div>', unsafe_allow_html=True)
       
        st.markdown('</div>', unsafe_allow_html=True)
       
        # Feature highlights
        st.markdown("---")
        st.markdown("### ✨ Features")
        col_feat1, col_feat2 = st.columns(2)
        with col_feat1:
            st.markdown("- 🧠 Context Retention")
            st.markdown("- 🔍 Semantic Search")
            st.markdown("- ⚡ Smart Queries")
        with col_feat2:
            st.markdown("- 📊 Auto Visualization")
            st.markdown("- 🎯 LLM Intent Analysis")
            st.markdown("- 💬 Multi-Chat Support")
   
    st.stop()

# ================= MAIN APP =================
# Header
col1, col2, col3 = st.columns([5, 3, 1])
with col1:
    st.title("🗄️ SQL Assistant Pro")
with col2:
    st.markdown(f"### Welcome, **{st.session_state.username}**! 👋")
with col3:
    if st.button("🚪 Logout", type="secondary"):
        # Close MySQL connection if open
        if st.session_state.custom_mysql_connection:
            try:
                if st.session_state.custom_mysql_connection.is_connected():
                    st.session_state.custom_mysql_connection.close()
            except:
                pass
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.current_chat_id = None
        st.session_state.db_mode = "system"
        st.session_state.active_custom_sqlite_path = None
        st.session_state.user_sqlite_dbs = []
        st.session_state.custom_mysql_params = {}
        st.session_state.custom_mysql_connection = None
        st.session_state.custom_schema = {}
        st.rerun()
st.divider()

# ================= IMPROVED SIDEBAR =================
with st.sidebar:
    st.title("⚙️ Control Panel")
    
    # ========== SECTION 1: DATABASE CONFIGURATION ==========
    with st.expander("🗄️ Database Configuration", expanded=True):
        db_modes = ["System DB (MySQL)", "Custom Persistent SQLite", "Custom MySQL Host"]
        selected_mode = st.radio(
            "Database Mode",
            db_modes,
            index=0 if st.session_state.db_mode == "system" else 1 if st.session_state.db_mode == "custom_sqlite" else 2,
            label_visibility="collapsed"
        )
        
        # Map to internal mode
        if selected_mode == "System DB (MySQL)":
            st.session_state.db_mode = "system"
        elif selected_mode == "Custom Persistent SQLite":
            st.session_state.db_mode = "custom_sqlite"
        elif selected_mode == "Custom MySQL Host":
            st.session_state.db_mode = "custom_mysql"
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # ===== SYSTEM DATABASE MODE =====
        if st.session_state.db_mode == "system":
            st.success("✅ Using System MySQL Database")
            db_id = "system_mysql"
            
            with st.container():
                render_table_selector(
                    st.session_state.business_schema,
                    db_mode="system",
                    db_id=db_id
                )
        
        # ===== CUSTOM SQLITE MODE =====
        elif st.session_state.db_mode == "custom_sqlite":
            # Active Database Display
            if st.session_state.active_custom_sqlite_path:
                db_id = st.session_state.active_custom_sqlite_path
                active_db_name = os.path.basename(st.session_state.active_custom_sqlite_path)
                st.info(f"📂 Active: **{active_db_name}**")
                
                render_table_selector(
                    st.session_state.custom_schema,
                    db_mode="custom_sqlite",
                    db_id=db_id
                )
                st.markdown("<br>", unsafe_allow_html=True)
            
            # Existing Databases Section
            if st.session_state.user_sqlite_dbs:
                with st.container():
                    st.markdown("##### 📚 Your Databases")
                    
                    db_options = [os.path.basename(path) for path in st.session_state.user_sqlite_dbs]
                    selected_db = st.selectbox(
                        "Select Database",
                        options=db_options,
                        label_visibility="collapsed",
                        key="select_existing_db"
                    )
                    selected_path = os.path.join(PERSISTENT_DB_DIR, selected_db)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("🔄 Load", use_container_width=True, key="load_db"):
                            st.session_state.active_custom_sqlite_path = selected_path
                            conn = sqlite3.connect(selected_path)
                            schema = get_database_schema(conn)
                            st.session_state.custom_schema = schema
                            conn.close()
                            st.success(f"✅ Loaded")
                            st.rerun()
                    
                    with col2:
                        if st.button("🗑️ Delete", use_container_width=True, type="secondary", key="delete_db"):
                            if st.session_state.active_custom_sqlite_path == selected_path:
                                st.session_state.active_custom_sqlite_path = None
                                st.session_state.custom_schema = {}
                            
                            try:
                                os.remove(selected_path)
                                st.session_state.user_sqlite_dbs = load_user_sqlite_dbs(st.session_state.user_id)
                                st.success(f"✅ Deleted")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {e}")
                    
                    # Show tables in selected database
                    if st.session_state.active_custom_sqlite_path == selected_path:
                        st.markdown("<br>", unsafe_allow_html=True)
                        conn = sqlite3.connect(selected_path)
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tables = [row[0] for row in cursor.fetchall()]
                        conn.close()
                        
                        if tables:
                            st.markdown("**📋 Tables:**")
                            table_info = get_table_info_from_sqlite(selected_path)
                            
                            for table in tables:
                                info = table_info.get(table, {})
                                row_count = info.get('row_count', 0)
                                col_count = info.get('column_count', 0)
                                
                                col_name, col_info, col_action = st.columns([4, 3, 1])
                                with col_name:
                                    st.markdown(f"`{table}`")
                                with col_info:
                                    st.caption(f"{row_count} rows • {col_count} cols")
                                with col_action:
                                    if st.button("🗑️", key=f"del_table_{table}", help="Delete table"):
                                        success, message = delete_table_from_sqlite(selected_path, table)
                                        if success:
                                            conn = sqlite3.connect(selected_path)
                                            schema = get_database_schema(conn)
                                            st.session_state.custom_schema = schema
                                            conn.close()
                                            st.success(message)
                                            st.rerun()
                                        else:
                                            st.error(message)
                            
                            # Add more tables to existing database
                            st.markdown("<br>", unsafe_allow_html=True)
                            with st.expander("➕ Add More Tables"):
                                add_files = st.file_uploader(
                                    "Upload files",
                                    type=['csv', 'xlsx', 'xls'],
                                    key="add_tables_uploader",
                                    accept_multiple_files=True,
                                    label_visibility="collapsed"
                                )
                                
                                if add_files:
                                    st.caption(f"📁 {len(add_files)} file(s) selected")
                                    
                                    if st.button("➕ Add to Database", use_container_width=True, type="primary"):
                                        with st.spinner("Adding tables..."):
                                            files_data = [(file.read(), file.name) for file in add_files]
                                            success, message, tables_added = add_tables_to_existing_sqlite(
                                                selected_path,
                                                files_data
                                            )
                                            
                                            if success:
                                                st.success(message)
                                                conn = sqlite3.connect(selected_path)
                                                schema = get_database_schema(conn)
                                                st.session_state.custom_schema = schema
                                                conn.close()
                                                st.rerun()
                                            else:
                                                st.error(message)
            
            # Create New Database Section
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("➕ Create New Database", expanded=not st.session_state.user_sqlite_dbs):
                new_db_name = st.text_input(
                    "Database Name",
                    placeholder="e.g., sales_data",
                    key="new_db_name"
                )
                
                uploaded_files = st.file_uploader(
                    "Upload Files (CSV/Excel)",
                    type=['csv', 'xlsx', 'xls'],
                    key="multi_file_uploader",
                    accept_multiple_files=True,
                    label_visibility="collapsed"
                )
                
                if uploaded_files:
                    st.caption(f"📁 {len(uploaded_files)} file(s) ready")
                
                if uploaded_files and new_db_name and st.button("📤 Create Database", use_container_width=True, type="primary"):
                    if not new_db_name.strip():
                        st.error("❌ Enter a database name")
                    else:
                        with st.spinner("Creating database..."):
                            files_data = [(file.read(), file.name) for file in uploaded_files]
                            
                            success, db_path, message, table_names = create_persistent_sqlite_with_multiple_tables(
                                files_data,
                                new_db_name,
                                st.session_state.user_id
                            )
                            
                            if success:
                                st.success(message)
                                st.session_state.user_sqlite_dbs = load_user_sqlite_dbs(st.session_state.user_id)
                                st.session_state.active_custom_sqlite_path = db_path
                                conn = sqlite3.connect(db_path)
                                schema = get_database_schema(conn)
                                st.session_state.custom_schema = schema
                                conn.close()
                                st.rerun()
                            else:
                                st.error(f"❌ {message}")
        
        # ===== CUSTOM MYSQL MODE =====
        elif st.session_state.db_mode == "custom_mysql":
            params = st.session_state.custom_mysql_params
            
            if params:
                db_id = f"{params['host']}|{params['database']}"
                st.info(f"🔌 Connected to **{params['database']}**")
                
                render_table_selector(
                    st.session_state.custom_schema,
                    db_mode="custom_mysql",
                    db_id=db_id
                )
                st.markdown("<br>", unsafe_allow_html=True)
            
            # MySQL Connection Form
            with st.expander("🔌 MySQL Connection", expanded=not params):
                with st.form("mysql_creds_form"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        host = st.text_input("Host", value=params.get("host", ""), placeholder="localhost")
                        port = st.number_input("Port", value=params.get("port", 3306), min_value=1, max_value=65535)
                        database = st.text_input("Database", value=params.get("database", ""), placeholder="mydb")
                    
                    with col2:
                        user = st.text_input("User", value=params.get("user", ""), placeholder="root")
                        password = st.text_input("Password", value=params.get("password", ""), type="password")
                        ssl_disabled = st.checkbox("Disable SSL", value=params.get("ssl_disabled", True))
                    
                    if not ssl_disabled:
                        ssl_ca = st.text_input("SSL CA Path", value=params.get("ssl_ca", ""), placeholder="/path/to/ca.pem")
                    else:
                        ssl_ca = ""
                    
                    connect_btn = st.form_submit_button("🔄 Connect", use_container_width=True, type="primary")
                    
                    if connect_btn:
                        if host and database and user and password:
                            new_params = {
                                "host": host,
                                "port": port,
                                "database": database,
                                "user": user,
                                "password": password,
                                "ssl_disabled": ssl_disabled,
                                "ssl_ca": ssl_ca
                            }
                            st.session_state.custom_mysql_params = new_params
                            
                            with st.spinner("Connecting..."):
                                conn = get_custom_mysql_connection_from_params(new_params)
                                if conn:
                                    st.session_state.custom_mysql_connection = conn
                                    schema = get_database_schema(conn)
                                    st.session_state.custom_schema = schema
                                    st.success("✅ Connected!")
                                    st.rerun()
                                else:
                                    st.error("❌ Connection failed")
                        else:
                            st.warning("⚠️ Fill all required fields")
            
            # Upload to MySQL
            if st.session_state.custom_mysql_connection:
                st.markdown("<br>", unsafe_allow_html=True)
                with st.expander("📤 Upload to MySQL"):
                    uploaded_file = st.file_uploader(
                        "Upload File",
                        type=['csv', 'xlsx', 'xls'],
                        key="mysql_uploader",
                        label_visibility="collapsed"
                    )
                    
                    if uploaded_file and st.button("📤 Upload", use_container_width=True, type="primary"):
                        with st.spinner("Uploading..."):
                            file_bytes = uploaded_file.read()
                            success, table_name, message = create_temp_database_from_mysql_file(
                                file_bytes,
                                uploaded_file.name,
                                st.session_state.custom_mysql_connection
                            )
                            
                            if success:
                                st.success(f"✅ {message}")
                                schema = get_database_schema(st.session_state.custom_mysql_connection)
                                st.session_state.custom_schema = schema
                                st.rerun()
                            else:
                                st.error(f"❌ {message}")
    
    # ========== SECTION 2: DATABASE SCHEMA ==========
    with st.expander("📊 Database Schema", expanded=False):
        schema_to_show = {}
        db_name = ""
        
        if st.session_state.db_mode == "system":
            schema_to_show = st.session_state.business_schema
            try:
                db_name = st.secrets["database"]["database"]
            except:
                db_name = "System Database"
        elif st.session_state.db_mode == "custom_sqlite" and st.session_state.active_custom_sqlite_path:
            conn = sqlite3.connect(st.session_state.active_custom_sqlite_path)
            schema_to_show = get_database_schema(conn)
            conn.close()
            db_name = os.path.basename(st.session_state.active_custom_sqlite_path)
        elif st.session_state.db_mode == "custom_mysql" and st.session_state.custom_mysql_connection:
            schema_to_show = st.session_state.custom_schema
            db_name = st.session_state.custom_mysql_params.get('database', 'MySQL')
        
        if schema_to_show:
            st.caption(f"🗄️ **{db_name}**")
            st.caption(f"📋 **{len(schema_to_show)} Tables**")
            st.markdown("<br>", unsafe_allow_html=True)
            
            for table_name, table_info in schema_to_show.items():
                with st.expander(f"**{table_name}** ({len(table_info['columns'])} cols)", expanded=False):
                    for col in table_info['columns']:
                        icon = "🔑" if col.get('key') == 'PRI' else "🔗" if col.get('key') == 'MUL' else "•"
                        col_type = col['type'].split('(')[0] if '(' in col['type'] else col['type']
                        st.caption(f"{icon} `{col['name']}` *{col_type}*")
                    
                    if table_info.get('relationships'):
                        st.markdown("**🔗 Relations:**")
                        for rel in table_info['relationships']:
                            st.caption(f"→ {rel['column']} ➜ {rel['references_table']}")
        else:
            st.info("No database selected")
    
    # ===== USER PROMPT CONTROL =====
    with st.expander("🧩 Prompt Customization", expanded=False):
        st.caption("Optional instructions to guide SQL generation")

        st.session_state.user_prompt_override = st.text_area(
            "Additional instructions (optional)",
            placeholder=(
                "Examples:\n"
                "- Prefer simple queries\n"
                "- Avoid joins if possible\n"
                "- Focus on business KPIs\n"
                "- Use strict filters only\n"
            ),
            height=120
        )

    # ========== SECTION 3: CHAT HISTORY ==========
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 💬 Chat History")
    
    if st.button("➕ New Chat", use_container_width=True, type="primary", key="new_chat_btn"):
        new_chat_id = create_new_chat(st.session_state.user_id, None)
        if new_chat_id:
            st.session_state.current_chat_id = new_chat_id
            st.rerun()
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    user_chats = get_user_chats(st.session_state.user_id)
    
    if user_chats:
        for chat in user_chats:
            is_active = chat['chat_id'] == st.session_state.current_chat_id
            display_title = chat['title'][:22] + "..." if len(chat['title']) > 25 else chat['title']
            
            col1, col2, col3 = st.columns([6, 2, 2])
            
            with col1:
                if st.button(
                    f"{'📌' if is_active else '💬'} {display_title}",
                    key=f"chat_{chat['chat_id']}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary"
                ):
                    st.session_state.current_chat_id = chat['chat_id']
                    st.rerun()
            
            with col2:
                if st.button("✏️", key=f"rename_{chat['chat_id']}", help="Rename", use_container_width=True):
                    st.session_state.show_rename_dialog = True
                    st.session_state.rename_chat_id = chat['chat_id']
                    st.rerun()
            
            with col3:
                if st.button("🗑️", key=f"del_{chat['chat_id']}", help="Delete", use_container_width=True):
                    st.session_state.show_delete_dialog = True
                    st.session_state.delete_chat_id = chat['chat_id']
                    st.rerun()
    else:
        st.info("No chats yet. Start chatting! 🚀")
    
    # ========== FOOTER INFO ==========
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.divider()
    
    with st.expander("ℹ️ About", expanded=False):
        st.caption("**Powered by Meta Llama 3.3**")
        st.caption("• 🧠 Context Retention")
        st.caption("• 🔍 Semantic Search")
        st.caption("• 🎯 Intent Analysis")
        st.caption("• ⚡ Multi-Table Queries")
        st.caption("• 🗄️ MySQL & SQLite Support")

# ================= DELETE CONFIRMATION DIALOG =================
if st.session_state.show_delete_dialog and st.session_state.delete_chat_id:
    @st.dialog("⚠️ Confirm Delete")
    def delete_dialog():
        user_chats = get_user_chats(st.session_state.user_id)
        chat_to_delete = next((c for c in user_chats if c['chat_id'] == st.session_state.delete_chat_id), None)
        
        if chat_to_delete:
            st.warning("⚠️ **This action cannot be undone!**")
            st.info(f"**Chat:** {chat_to_delete['title']}")
            st.markdown("<br>", unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🗑️ Delete", use_container_width=True, type="primary"):
                    if st.session_state.delete_chat_id == st.session_state.current_chat_id:
                        other_chats = [c for c in user_chats if c['chat_id'] != st.session_state.delete_chat_id]
                        st.session_state.current_chat_id = other_chats[0]['chat_id'] if other_chats else None
                    
                    success, message = delete_chat(st.session_state.delete_chat_id, st.session_state.user_id)
                    
                    if success:
                        st.success(message)
                        st.session_state.show_delete_dialog = False
                        st.session_state.delete_chat_id = None
                        st.rerun()
                    else:
                        st.error(message)
            
            with col2:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state.show_delete_dialog = False
                    st.session_state.delete_chat_id = None
                    st.rerun()
    
    delete_dialog()

# ================= RENAME DIALOG =================
if st.session_state.show_rename_dialog and st.session_state.rename_chat_id:
    @st.dialog("✏️ Rename Chat")
    def rename_dialog():
        user_chats = get_user_chats(st.session_state.user_id)
        current_chat = next((c for c in user_chats if c['chat_id'] == st.session_state.rename_chat_id), None)
        
        if current_chat:
            new_title = st.text_input(
                "New title",
                value=current_chat['title'],
                max_chars=255,
                key="rename_input",
                label_visibility="collapsed"
            )
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("💾 Save", use_container_width=True, type="primary"):
                    if new_title and new_title.strip():
                        success, message = rename_chat(
                            st.session_state.rename_chat_id,
                            st.session_state.user_id,
                            new_title
                        )
                        
                        if success:
                            st.success(message)
                            st.session_state.show_rename_dialog = False
                            st.session_state.rename_chat_id = None
                            st.rerun()
                        else:
                            st.error(message)
                    else:
                        st.error("Title cannot be empty")
            
            with col2:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state.show_rename_dialog = False
                    st.session_state.rename_chat_id = None
                    st.rerun()
    
    rename_dialog()


# ================= MAIN CHAT INTERFACE =================

# ──────────────────────────────────────────────
#  HEADER / TITLE
# ──────────────────────────────────────────────
st.info("🤖 **Powered by Meta Llama 3.3 70B** - Lightning-fast context-aware SQL generation with LLM-based intent analysis!")

# ──────────────────────────────────────────────
#  WELCOME SCREEN (shown when no active chat)
# ──────────────────────────────────────────────
if not st.session_state.get("current_chat_id"):
    st.markdown("## 👋 Welcome to SQL Assistant Pro!")
    st.markdown("### Enhanced with Meta Llama 3.3 via Groq API")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🧠 Context Features")
        st.markdown("- ✅ **Retains Last 5 Messages** - Recent context")
        st.markdown("- 📝 **Summarizes Older Chats** - Long-term memory")
        st.markdown("- 🔍 **Semantic Search** - Finds similar Q&As")
        st.markdown("- 💡 **Smart Context Window** - Optimized tokens")

    with col2:
        st.markdown("#### ⚡ Query Intelligence")
        st.markdown("- 🎯 **LLM Intent Analysis** - Smart table detection")
        st.markdown("- 🔗 **JOIN When Needed** - Performance first")
        st.markdown("- 📊 **Multi-Table Analysis** - Complex queries")
        st.markdown("- 🚀 **Single-Table Preference** - Speed optimized")

    st.markdown("---")
    st.markdown("### 💡 Example Questions:")

    ex_col1, ex_col2 = st.columns(2)

    with ex_col1:
        st.markdown("**Single-Table Queries:**")
        st.markdown("- 'Show me red sneakers for women'")
        st.markdown("- 'Find all Nike products'")
        st.markdown("- 'What shoes cost under ₹2000?'")
        st.markdown("- 'List athletic footwear'")

    with ex_col2:
        st.markdown("**Multi-Table Queries:**")
        st.markdown("- 'What are our best-selling products?'")
        st.markdown("- 'Total revenue by product category'")
        st.markdown("- 'Which customers bought Nike shoes?'")
        st.markdown("- 'Sales performance analysis'")

# ──────────────────────────────────────────────
#  CHAT HISTORY (shown when active chat exists)
# ──────────────────────────────────────────────
else:
    chat_history = get_chat_history(
        st.session_state.current_chat_id,
        st.session_state.user_id
    )

    for turn_idx, turn in enumerate(chat_history):
        # USER MESSAGE
        with st.chat_message("user"):
            st.write(turn["question"])
            st.markdown(
                create_copy_button(turn["question"], "📋 Copy Question"),
                unsafe_allow_html=True
            )

        # ASSISTANT MESSAGE
        with st.chat_message("assistant"):
            render_assistant_response(
                summary=turn.get("response"),
                df=turn.get("result_df"),
                visualization=turn.get("visualization"),
                query=turn.get("query_generated"),
                intent_analysis=turn.get("intent_analysis"),
                context_stats=turn.get("context_stats"),
                llm_meta=turn.get("llm_meta"),
                is_sqlite=turn.get("is_sqlite", False),
                message_key=f"history_{turn_idx}"
            )

# ──────────────────────────────────────────────
#  CHAT INPUT – ALWAYS AT THE BOTTOM (this fixes the duplicate key error)
# ──────────────────────────────────────────────
user_question = st.chat_input(
    "💬 Ask about your data...",
    key="main_chat_input"
)

# ──────────────────────────────────────────────
#  HANDLE USER INPUT
# ──────────────────────────────────────────────
if user_question:
    # 1. If no chat exists → create one now
    if not st.session_state.get("current_chat_id"):
        new_chat_id = create_new_chat(
        user_id=st.session_state.user_id,
        first_question=user_question
    )
        st.session_state.current_chat_id = new_chat_id

        # Generate & set smart title
        # new_title = generate_smart_chat_title(user_question)
        # rename_chat(new_chat_id, st.session_state.user_id, new_title)

        # Force rerun to show chat interface instead of welcome screen
        st.rerun()

    # 2. Show the user's message immediately
    with st.chat_message("user"):
        st.write(user_question)
        st.markdown(
            create_copy_button(user_question, "📋 Copy Question"),
            unsafe_allow_html=True
        )

    # 3. Generate assistant response
    with st.chat_message("assistant"):
        with st.spinner("🤔 Analyzing with Llama 3.3..."):
            try:
                # Get current chat history
                chat_history = get_chat_history(
                    st.session_state.current_chat_id,
                    st.session_state.user_id
                )

                # Build context
                context, context_stats = build_optimized_context(chat_history, user_question)

                # Determine active connection & schema
                active_conn = None
                active_schema = {}
                is_sqlite = False

                if st.session_state.db_mode == "system":
                    active_conn = get_business_db_connection()
                    active_schema = st.session_state.business_schema
                elif st.session_state.db_mode == "custom_sqlite" and st.session_state.get("active_custom_sqlite_path"):
                    active_conn = sqlite3.connect(st.session_state.active_custom_sqlite_path)
                    active_schema = st.session_state.custom_schema
                    is_sqlite = True
                elif st.session_state.db_mode == "custom_mysql" and st.session_state.get("custom_mysql_connection"):
                    active_conn = st.session_state.custom_mysql_connection
                    active_schema = st.session_state.custom_schema

                if not active_conn:
                    response = "⚠️ No database connected. Please select and configure a database mode in the sidebar."
                    st.error(response)
                    save_chat_turn(
                        st.session_state.current_chat_id,
                        st.session_state.user_id,
                        user_question,
                        None,
                        response,
                        None
                    )
                    st.stop()

                # Intent analysis
                with st.spinner("🧠 Analyzing query intent..."):
                    filtered_schema = get_filtered_schema_for_active_db(active_schema)

                    if not filtered_schema:
                        st.error("⚠️ No tables selected for this database. Please select tables from the sidebar.")
                        st.stop()

                    intent_analysis = analyze_query_intent_with_llm(user_question, filtered_schema)
                
                # 🔒 Enforce table whitelist
                intent_analysis["tables_needed"] = [
                    t for t in intent_analysis["tables_needed"]
                    if t in filtered_schema
                ]

                # with st.expander("🐞 DEBUG: Filtered Schema Sent to LLM", expanded=False):
                #     st.write("Tables in filtered schema:")
                #     st.json(list(filtered_schema.keys()))

                # st.info(f"🎯 Intent: {intent_analysis['intent_type']} | Tables: {', '.join(intent_analysis['tables_needed'])}")

                
                # Format schema
                # schema_text = format_schema_for_llm(active_schema, intent_analysis['tables_needed'])
                schema_text = format_schema_for_llm(
                filtered_schema,
                tables_to_include=intent_analysis["tables_needed"]
            )
                # with st.expander("🐞 DEBUG: Schema Text in Prompt", expanded=False):
                #     st.text(schema_text)
                

                if not filtered_schema:
                    st.error("⚠️ No tables selected. Please select tables from the sidebar.")
                    st.stop()

        
                # Generate SQL
                query_result = generate_sql_query(
                    user_question,
                    schema_text,
                    context,
                    intent_analysis,
                    is_sqlite=is_sqlite,
                    user_prompt_override=st.session_state.get("user_prompt_override", "")
                )

                if not query_result["success"]:
                    response = f"❌ Could not generate query: {query_result.get('error', 'Unknown')}"
                    st.error(response)
                    if query_result.get("query"):
                        st.code(query_result["query"], language="sql")
                    save_chat_turn(
                        st.session_state.current_chat_id,
                        st.session_state.user_id,
                        user_question,
                        query_result.get("query"),
                        response,
                        None
                    )
                else:
                    query = query_result["query"]
                    exec_result = execute_query(active_conn, query)

                    if not exec_result["success"]:
                        response = f"❌ Query failed: {exec_result.get('error', 'Unknown')}"
                        st.error(response)
                        st.warning("**Available tables in database:**")
                        for table_name in active_schema.keys():
                            st.write(f"• {table_name}")
                        with st.expander("🔍 View Failed Query"):
                            st.code(query, language="sql")
                            st.markdown(create_copy_button(query, "📋 Copy Query"), unsafe_allow_html=True)
                        save_chat_turn(
                            st.session_state.current_chat_id,
                            st.session_state.user_id,
                            user_question,
                            query,
                            response,
                            None
                        )
                    else:
                        sql_tokens = query_result["tokens"]

                        # Generate final response + viz
                        summary, df, visualization, llm_meta = generate_db_response_with_presentation(
                            user_question,
                            query,
                            exec_result,
                            context ,
                            sql_tokens=sql_tokens
                        )

                        render_assistant_response(
                            summary=summary,
                            df=df,
                            visualization=visualization,
                            query=query,
                            intent_analysis=intent_analysis,
                            context_stats=context_stats,
                            llm_meta=llm_meta,
                            is_sqlite=is_sqlite,
                            message_key=f"live_{len(chat_history)}"
                        )

                        save_chat_turn(
                            st.session_state.current_chat_id,
                            st.session_state.user_id,
                            user_question,
                            query,
                            summary,
                            df if df is not None and not df.empty else None
                        )

            except Exception as e:
                response = f"❌ Unexpected error: {str(e)}"
                st.error(response)
                st.exception(e)
                save_chat_turn(
                    st.session_state.current_chat_id,
                    st.session_state.user_id,
                    user_question,
                    None,
                    response,
                    None
                )

            finally:
                # Clean up connection if needed
                if active_conn and st.session_state.db_mode != "custom_mysql":
                    try:
                        if is_sqlite:
                            active_conn.close()
                        elif hasattr(active_conn, 'is_connected') and active_conn.is_connected():
                            active_conn.close()
                    except:
                        pass
# ================= FOOTER =================
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    st.caption("🤖 Powered by Meta Llama 3.3 70B via Groq")
with col2:
    db_status = {
        "system": "System DB (MySQL)",
        "custom_sqlite": "Custom Persistent SQLite",
        "custom_mysql": "Custom MySQL Host"
    }.get(st.session_state.db_mode, "Unknown")
    st.caption(f"🗄️ {db_status}")
with col3:
    st.caption("🧠 Context-Aware + ⚡ Smart Queries")