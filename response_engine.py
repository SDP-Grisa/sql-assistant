import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from groq import Groq
from datetime import datetime
from typing import Dict, List, Tuple, Optional


# ================= RESPONSE GENERATION =================
def generate_db_response_with_presentation(
    question: str,
    query: str,
    result: Dict,
    context: str
) -> Tuple[str, Optional[pd.DataFrame], Optional[go.Figure]]:
    """Generate natural language response with visualization using Groq Llama"""
    try:
        client = Groq(api_key=st.secrets["groq"]["api_key"])
       
        df = result.get("data")
        if df is None or df.empty:
            return "No results found for your query.", None, None
       
        # Dynamic sample data: Use fewer rows for large datasets
        sample_rows = min(5, len(df))  # Show max 5 rows in summary
        data_summary = f"Query returned {len(df)} rows with columns: {', '.join(df.columns.tolist())}\n\n"
        data_summary += f"Sample data (first {sample_rows} rows):\n{df.head(sample_rows).to_string()}"
       
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": f"""Context: {context}
Question: {question}
SQL Query Executed: {query}
Results: {data_summary}
Provide a natural, conversational response summarizing these results. Be concise but informative. Highlight key findings."""
            }],
            max_tokens=800,
            temperature=0.7
        )

        prompt_text = f"""
        Provide a user-friendly response using this format:

        - Start with a short direct answer (1–2 lines)
        - Then show key insights as bullet points
        - Avoid mentioning SQL or tables
        - Do NOT dump raw numbers unless meaningful
        - Assume the user is non-technical

        Context: {context}
        Question: {question}
        SQL Query Executed: {query}
        Results: {data_summary}
        """

        usage = response.usage if hasattr(response, "usage") else None
       
        summary = response.choices[0].message.content
       
        # Generate visualization if appropriate
        visualization = create_visualization_if_applicable(df, question)
       
        return summary, df, visualization, {
        "prompt": prompt_text,
        "input_tokens": usage.prompt_tokens if usage else None,
        "output_tokens": usage.completion_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None
    }
       
    except Exception as e:
        st.error(f"Response generation error: {e}")
        return f"Found {len(df)} results.", df, None

def create_visualization_if_applicable(df: pd.DataFrame, question: str) -> Optional[go.Figure]:
    """Create appropriate visualization based on data and question - Enhanced for robustness"""
    if df.empty or len(df) > 50:  # Reduced threshold for performance
        return None
   
    question_lower = question.lower()
   
    # Detect column types more robustly
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    date_cols = df.select_dtypes(include=['datetime']).columns.tolist()
   
    if not numeric_cols:
        return None
   
    # Improved detection for top-N or ranking queries
    if any(word in question_lower for word in ['top', 'best', 'most', 'highest', 'lowest', 'rank', 'order']):
        # Find likely x (categorical) and y (numeric) columns
        if categorical_cols and numeric_cols:
            x_col = categorical_cols[0]  # Default to first categorical
            y_col = numeric_cols[0]      # Default to first numeric
            # Heuristic: Prefer 'name' or 'id' for x, 'score', 'marks', 'price' for y
            if any('name' in col.lower() or 'id' in col.lower() for col in categorical_cols):
                x_col = next((col for col in categorical_cols if 'name' in col.lower() or 'id' in col.lower()), x_col)
            if any('marks' in col.lower() or 'score' in col.lower() or 'price' in col.lower() or 'salary' in col.lower() for col in numeric_cols):
                y_col = next((col for col in numeric_cols if any(kw in col.lower() for kw in ['marks', 'score', 'price', 'salary'])), y_col)
            
            fig = px.bar(
                df.head(20),  # Limit for performance
                x=x_col,
                y=y_col,
                title=f"Top Results: {x_col.title()} by {y_col.title()}",
                color=y_col,
                color_continuous_scale='viridis'
            )
            fig.update_layout(xaxis_tickangle=-45, showlegend=False)
            return fig
   
    # Distribution or breakdown
    if any(word in question_lower for word in ['distribution', 'breakdown', 'by', 'group']):
        if categorical_cols and numeric_cols:
            fig = px.pie(
                df.head(10),
                names=categorical_cols[0],
                values=numeric_cols[0],
                title=f"Distribution by {categorical_cols[0].title()}"
            )
            return fig
   
    # Basic line chart for time-series if dates present
    if date_cols and numeric_cols:
        fig = px.line(
            df,
            x=date_cols[0],
            y=numeric_cols[0],
            title=f"Trend: {numeric_cols[0].title()} over Time"
        )
        return fig
   
    return None

def is_product_data(df: pd.DataFrame) -> bool:
    """Enhanced check for product-like data - Requires multiple specific columns"""
    product_indicators = ['product_name', 'name', 'brand', 'price', 'selling_price', 'category', 'mrp', 'discount']
    col_lowers = [col.lower() for col in df.columns]
    # Require at least 3 product indicators, including price-like and category/brand
    price_like = any(ind in col_lowers for ind in ['price', 'selling_price', 'mrp'])
    cat_brand_like = any(ind in col_lowers for ind in ['category', 'brand'])
    count = sum(1 for ind in product_indicators if ind in col_lowers)
    return count >= 3 and price_like and cat_brand_like

def display_generic_row(row: Dict, idx: int) -> None:
    """Display a generic row as an expandable card with key-value pairs"""
    # Use first non-numeric column as header (e.g., name or id)
    header_key = next((k for k in row if isinstance(row[k], str) and len(str(row[k])) < 50), list(row.keys())[0])
    header_value = row[header_key]
    with st.expander(f"📄 Row {idx+1}: {header_value}", expanded=False):
        st.markdown('<div class="data-row-card">', unsafe_allow_html=True)
        cols = st.columns(2)
        for i, (key, value) in enumerate(row.items()):
            with cols[i % 2]:
                # Format values: Currency for price-like, dates, etc.
                if any(kw in key.lower() for kw in ['price', 'salary', 'cost']) and isinstance(value, (int, float)):
                    st.markdown(f"**{key.replace('_', ' ').title()}:** ₹{value:,.2f}")
                elif isinstance(value, datetime):
                    st.markdown(f"**{key.replace('_', ' ').title()}:** {value.strftime('%Y-%m-%d')}")
                else:
                    st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")
        st.markdown('</div>', unsafe_allow_html=True)
