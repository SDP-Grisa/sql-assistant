# db_chat_manager.py
import streamlit as st
import pandas as pd
from typing import Optional, List, Dict, Tuple
from mysql.connector import Error
import mysql.connector
import base64
import tempfile
from datetime import datetime

# from db_connection import get_auth_db_connection


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



# ================= CHAT MANAGEMENT FUNCTIONS =================
def create_new_chat(user_id: int, first_question: Optional[str]) -> Optional[int]:
    """Create new chat session with auto-generated title"""
    connection = get_auth_db_connection()
    if not connection:
        st.error("Failed to connect to database for chat creation")
        return None

    try:
        cursor = connection.cursor()

        # ✅ Generate title here (single source of truth)
        chat_title = generate_smart_chat_title(first_question) if first_question else "New Chat"

        cursor.execute(
            "INSERT INTO chats (user_id, title) VALUES (%s, %s)",
            (user_id, chat_title)
        )
        connection.commit()
        return cursor.lastrowid

    except Error as e:
        st.error(f"Chat creation error: {e}")
        return None

    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


def get_user_chats(user_id: int) -> List[Dict]:
    """Get all chats for user"""
    connection = get_auth_db_connection()
    if not connection:
        return []
   
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT chat_id, title, created_at FROM chats WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        return cursor.fetchall()
    except Error as e:
        st.error(f"Chat fetch error: {e}")
        return []
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def get_chat_history(chat_id: int, user_id: int) -> List[Dict]:
    """Get chat history with verification"""
    connection = get_auth_db_connection()
    if not connection:
        return []
   
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT ch.question, ch.query_generated, ch.response, ch.result_data, ch.timestamp
            FROM chat_history ch
            JOIN chats c ON ch.chat_id = c.chat_id
            WHERE ch.chat_id = %s AND c.user_id = %s
            ORDER BY ch.timestamp ASC
        """, (chat_id, user_id))
       
        results = cursor.fetchall()
       
        # Parse result_data JSON back to DataFrame if it exists
        for result in results:
            if result.get('result_data'):
                try:
                    result['result_df'] = pd.read_json(result['result_data'])
                except:
                    result['result_df'] = None
            else:
                result['result_df'] = None
       
        return results
    except Error as e:
        st.error(f"History fetch error: {e}")
        return []
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def save_chat_turn(chat_id: int, user_id: int, question: str, query: Optional[str], response: str, result_df: Optional[pd.DataFrame] = None) -> bool:
    """Save chat turn with verification and result data"""
    connection = get_auth_db_connection()
    if not connection:
        return False
   
    try:
        cursor = connection.cursor()
       
        # Verify chat belongs to user
        cursor.execute("SELECT user_id FROM chats WHERE chat_id = %s", (chat_id,))
        result = cursor.fetchone()
       
        if not result or result[0] != user_id:
            return False
       
        # Convert DataFrame to JSON if it exists
        result_data = None
        if result_df is not None and not result_df.empty:
            result_data = result_df.to_json()
       
        cursor.execute(
            "INSERT INTO chat_history (chat_id, user_id, question, query_generated, response, result_data) VALUES (%s, %s, %s, %s, %s, %s)",
            (chat_id, user_id, question, query, response, result_data)
        )
        connection.commit()
        return True
    except Error as e:
        st.error(f"Save error: {e}")
        return False
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def rename_chat(chat_id: int, user_id: int, new_title: str) -> Tuple[bool, str]:
    """Rename chat with verification"""
    connection = get_auth_db_connection()
    if not connection:
        return False, "Database connection failed"
   
    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE chats SET title = %s WHERE chat_id = %s AND user_id = %s",
            (new_title, chat_id, user_id)
        )
        connection.commit()
       
        if cursor.rowcount > 0:
            return True, "Chat renamed successfully"
        return False, "Chat not found or access denied"
    except Error as e:
        return False, f"Rename error: {e}"
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def delete_chat(chat_id: int, user_id: int) -> Tuple[bool, str]:
    """Delete chat with verification"""
    connection = get_auth_db_connection()
    if not connection:
        return False, "Database connection failed"
   
    try:
        cursor = connection.cursor()
       
        # Delete history first (handled by CASCADE, but being explicit)
        cursor.execute(
            "DELETE FROM chat_history WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id)
        )
       
        # Delete chat
        cursor.execute(
            "DELETE FROM chats WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id)
        )
        connection.commit()
       
        if cursor.rowcount > 0:
            return True, "Chat deleted successfully"
        return False, "Chat not found or access denied"
    except Error as e:
        return False, f"Delete error: {e}"
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def generate_smart_chat_title(question: str, max_len: int = 50) -> str:
    if not question:
        return datetime.now().strftime("%d %b %I:%M %p")

    question = question.strip()

    if len(question) <= max_len:
        return question

    return question[:max_len].rsplit(" ", 1)[0] + "..."
