import streamlit as st

def get_selected_table_set(db_mode: str, db_id: str) -> set:
    """
    Returns the selected table set for a specific database.
    Creates it if it doesn't exist.
    """
    bucket = st.session_state.selected_tables[db_mode]
    if db_id not in bucket:
        bucket[db_id] = set()
    return bucket[db_id]


def render_table_selector(schema: dict, db_mode: str, db_id: str):
    st.markdown("### 📋 Select Tables for Q&A")

    selected_tables = get_selected_table_set(db_mode, db_id)

    for table_name, meta in schema.items():
        checked = table_name in selected_tables

        is_checked = st.checkbox(
            f"{table_name} ({meta.get('row_count', '?')} rows)",
            value=checked,
            key=f"{db_mode}_{db_id}_{table_name}"
        )

        if is_checked:
            selected_tables.add(table_name)
        else:
            selected_tables.discard(table_name)

    # ✅ DEBUG (temporary)
    st.caption(f"Selected tables for this DB: {list(selected_tables)}")
