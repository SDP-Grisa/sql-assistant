# sql-assistant

# 🗄️ SQL Assistant Pro

> **An AI-powered, context-aware SQL chat application built with Streamlit and Meta Llama 3.3 via Groq.**

Ask questions about your data in plain English. Get SQL queries, intelligent summaries, and interactive visualizations — all in a conversational multi-chat interface.

---

## ✨ Features

### 🧠 Intelligent Context Management
- **Recent 5 messages** retained verbatim for immediate context
- **Older messages summarized** via LLM for long-term memory without token bloat
- **Semantic search** using `sentence-transformers` — finds top 3 historically similar Q&A pairs and injects them as relevant context

### 🎯 LLM-Based Query Intent Analysis
- Before generating SQL, uses Llama 3.3 to analyze intent: single-table vs. multi-table, JOIN necessity, which tables are needed
- Enforces a **user-selected table whitelist** to prevent hallucinated or unauthorized table access

### ⚡ Smart SQL Generation
- Context-aware SQL via a structured, role-based system prompt
- Supports **filter accumulation** across turns (e.g., "now show only red ones" correctly carries forward prior filters)
- Detects **context resets** (new domain = fresh WHERE clause)
- Prefers single-table queries for performance; uses JOINs only when necessary
- Supports both **MySQL** and **SQLite** dialects automatically

### 📊 Rich Response Display
- **Card-based UI** for query results with key fields highlighted
- Auto-generated **Plotly visualizations** (bar, pie, line charts based on data + question type)
- Response tabs: `📝 Answer & Data` | `📈 Chart` | `🧠 SQL Query` | `🧪 Debug`
- Full dataset accessible in a collapsible expander with **CSV download**

### 🗄️ Multi-Database Support

| Mode | Description |
|------|-------------|
| **System MySQL** | Pre-configured production MySQL database |
| **Custom Persistent SQLite** | Upload CSV/Excel → auto-converted to SQLite, persisted per user |
| **Custom MySQL Host** | Connect to any external MySQL instance via UI-based credential form |

### 👤 Authentication
- User registration and login with SHA-256 password hashing
- All chat history scoped to authenticated users
- SQLite databases namespaced by `user_id` for isolation

### 💬 Multi-Chat Interface
- Create, rename, and delete multiple independent chat sessions
- Each session retains its own full history
- Auto-generated smart chat titles from first question

---

## 🗂️ Project Structure

```
.
├── app.py                   # Main Streamlit app (auth, routing, chat UI, SQL pipeline)
├── db_chat_manager.py       # Chat CRUD: create, rename, delete, save turns, fetch history
├── response_engine.py       # LLM response generation, Plotly visualizations, display helpers
├── file_db_manager.py       # SQLite DB creation from CSV/Excel, table management
├── db_table_selector.py     # Sidebar table selection widget + session state management
└── custom_dbs/              # Persistent SQLite databases (auto-created, per-user)
```

---

## ⚙️ How It Works

```
User Question
     │
     ▼
Build Context (recent + summarized older + semantic similar)
     │
     ▼
LLM Intent Analysis → Which tables? Single or multi-table?
     │
     ▼
Filter Schema (user-whitelisted tables only)
     │
     ▼
Generate SQL (Llama 3.3 via Groq)
     │
     ▼
Execute Query (MySQL or SQLite)
     │
     ▼
Generate Summary + Visualization (Llama 3.3 + Plotly)
     │
     ▼
Display Cards + Tabs + Save to Chat History
```

---

## 🚀 Setup & Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd sql-assistant-pro
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Key dependencies:

```
streamlit
mysql-connector-python
pandas
plotly
groq
sentence-transformers
scikit-learn
numpy
sqlalchemy
openpyxl
```

### 3. Configure secrets

Create `.streamlit/secrets.toml`:

```toml
[groq]
api_key = "your_groq_api_key"

[database]
host     = "your-business-db-host"
port     = 3306
database = "your_db_name"
user     = "your_user"
password = "your_password"
ssl_disabled = false
ssl_ca_b64   = "base64_encoded_ssl_cert"   # optional

[auth_database]
host     = "your-auth-db-host"
port     = 3306
database = "auth_db"
user     = "your_user"
password = "your_password"
ssl_disabled = false
ssl_ca_b64   = "base64_encoded_ssl_cert"   # optional
```

> **SSL Note:** Provide your SSL CA certificate as a Base64-encoded string in `ssl_ca_b64`. The app decodes it to a temp `.pem` file at runtime.

### 4. Run the app

```bash
streamlit run app.py
```

---

## 🗃️ Database Setup

### Auth database (auto-initialized on first run)

The app automatically creates these tables:

```sql
CREATE TABLE users (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(64) NOT NULL,
    email         VARCHAR(100),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chats (
    chat_id    INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    title      VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE chat_history (
    history_id     INT AUTO_INCREMENT PRIMARY KEY,
    chat_id        INT NOT NULL,
    user_id        INT NOT NULL,
    question       TEXT,
    query_generated TEXT,
    response       TEXT,
    result_data    LONGTEXT,
    timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
);
```

### Migrating from an older version?

```sql
ALTER TABLE chat_history ADD COLUMN result_data LONGTEXT AFTER response;
```

---

## 🧩 Module Reference

### `app.py`
The main Streamlit entry point. Handles login/signup, sidebar database configuration, the table selector, chat session management, and the full per-question pipeline: context → intent → schema filtering → SQL generation → execution → response rendering.

### `db_chat_manager.py`
All MySQL chat persistence:
- `create_new_chat()` — creates a chat with an auto-generated title
- `get_user_chats()` — lists all chats for a user
- `get_chat_history()` — fetches turn history, deserializes stored DataFrames from JSON
- `save_chat_turn()` — saves question, SQL, response text, and result DataFrame
- `rename_chat()` / `delete_chat()` — chat management with user verification

### `response_engine.py`
- `generate_db_response_with_presentation()` — calls Llama 3.3 to produce a user-friendly natural-language summary from query results, returns token usage metadata
- `create_visualization_if_applicable()` — auto-selects bar, pie, or line chart based on data shape and question keywords
- `is_product_data()` — heuristic to detect product-like schemas (requires price + category/brand columns)
- `display_generic_row()` — renders any DB row as a formatted key-value card

### `file_db_manager.py`
- `create_persistent_sqlite_with_multiple_tables()` — converts uploaded CSV/Excel files into named tables in a per-user SQLite file under `custom_dbs/`
- `add_tables_to_existing_sqlite()` — appends new tables to an existing SQLite database
- `delete_table_from_sqlite()` — drops a specific table
- `get_table_info_from_sqlite()` — returns row count and column count per table
- `create_temp_database_from_mysql_file()` — loads a CSV/Excel into a custom MySQL connection via SQLAlchemy

### `db_table_selector.py`
- `render_table_selector()` — renders sidebar checkboxes for selecting which tables to expose to the LLM
- `get_selected_table_set()` — manages per-database, per-mode selection state in `st.session_state`

---

## 💬 Example Queries

**Single-table:**
- "Show me all red sneakers for women"
- "Find all Nike products under ₹2000"
- "List athletic footwear sorted by price"

**Multi-table / analytical:**
- "What are our best-selling products?"
- "Total revenue by product category"
- "Which customers bought Nike shoes last month?"

**Conversational refinement (filter accumulation):**
```
User: "Show me kurtis"
User: "Only pink ones"        ← carries forward category filter
User: "Size M only"           ← carries forward category + color filter
```

---

## 🔒 Security Notes

- Passwords stored as **SHA-256 hashes** — never plaintext
- Custom MySQL credentials live only in **Streamlit session state** — not persisted to disk
- SQLite files are **namespaced by `user_id`** — no cross-user access
- The LLM only sees **user-selected tables** — not the full database schema

---

## 📄 License

This project is proprietary. Contact the author for usage permissions.