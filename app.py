"""ExpenseGuard AI - MCP-powered workplace expense report checker."""

import os
import sys
import hashlib
import html

import pandas as pd
import streamlit as st

from config import ExpenseGuardConfig
from agent import ExpenseAuditAgent
from mcp_client import SyncMCPExpenseClient
from llm import OllamaClient
from report_gen import generate_excel_report, generate_csv_report
from doc_loader import load_single_file, load_documents_batch


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="ExpenseGuard AI — Finance Report Checker",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# STYLING
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif;
}

.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 3rem;
    max-width: 1500px;
}

[data-testid="stSidebar"] {
    border-right: 1px solid #E2E8F0;
}

.eg-header {
    background: linear-gradient(135deg, #0F172A 0%, #1E1B4B 50%, #312E81 100%);
    border-radius: 18px;
    padding: 26px 30px;
    margin-bottom: 24px;
    color: white;
    box-shadow: 0 12px 28px -8px rgba(15, 23, 42, .25);
}

.eg-header h1 {
    color: white;
    font-size: 29px;
    font-weight: 800;
    margin: 0;
    letter-spacing: -.5px;
}

.eg-header p {
    color: #CBD5E1;
    font-size: 14px;
    margin-top: 8px;
    margin-bottom: 0;
}

.eg-badge {
    display: inline-block;
    background: rgba(99,102,241,.2);
    border: 1px solid rgba(129,140,248,.4);
    color: #C7D2FE;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 11px;
    margin: 4px;
    white-space: nowrap;
}

.eg-section {
    background: linear-gradient(135deg, #F8FAFC, #EEF2FF);
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 16px 20px;
    margin: 12px 0 18px 0;
}

.eg-section-title {
    color: #1E1B4B;
    font-size: 17px;
    font-weight: 800;
    margin-bottom: 4px;
}

.eg-section-subtitle {
    color: #64748B;
    font-size: 12px;
}

div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 17px 18px;
    box-shadow: 0 3px 10px rgba(15, 23, 42, .035);
}

div[data-testid="stMetricLabel"] {
    color: #64748B;
    font-size: 12px;
    font-weight: 600;
}

div[data-testid="stMetricValue"] {
    color: #0F172A;
    font-weight: 800;
}

div[data-testid="stMetricDelta"] {
    font-size: 12px;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 1px solid #E2E8F0;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 9px 9px 0 0;
    padding: 10px 16px;
    font-weight: 600;
}

.stTabs [aria-selected="true"] {
    background: #EEF2FF;
}

div[data-testid="stDataFrame"] {
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    overflow: hidden;
}

.stButton > button,
.stDownloadButton > button {
    border-radius: 9px;
    font-weight: 700;
    min-height: 42px;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #4F46E5, #4338CA);
    border: none;
}

.xai-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #F59E0B;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 16px;
}

.xai-critical {
    border-left-color: #EF4444;
}

.xai-valid {
    border-left-color: #10B981;
}

.xai-evidence {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    padding: 10px;
    border-radius: 8px;
    margin: 8px 0;
}

.eg-status {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    background: #EEF2FF;
    color: #3730A3;
}

.eg-footer {
    color: #64748B;
    font-size: 12px;
    text-align: center;
    padding: 12px 0;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# SESSION STATE
# ============================================================

if "config" not in st.session_state:
    st.session_state.config = ExpenseGuardConfig()

if "audit_result" not in st.session_state:
    st.session_state.audit_result = None

if "current_df" not in st.session_state:
    st.session_state.current_df = None

if "file_name" not in st.session_state:
    st.session_state.file_name = None

if "upload_signature" not in st.session_state:
    st.session_state.upload_signature = None

if "agent_logs" not in st.session_state:
    st.session_state.agent_logs = []


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def money(value):
    try:
        if value is None or pd.isna(value):
            return "—"
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def load_file_records(file_obj, filename):
    """Use the existing document loader for supported uploads."""
    file_obj.seek(0)
    return load_single_file(file_obj, filename)


def execute_audit(df, filename, mode="full", use_llm=True):
    """Run the expense agent and save the audit results."""
    if df is None or df.empty:
        st.warning("No expense records were found.")
        return

    records = df.where(pd.notnull(df), None).to_dict(orient="records")

    with st.spinner("🤖 AI Agent is coordinating MCP validation tools..."):
        agent = ExpenseAuditAgent(st.session_state.config)
        result = agent.run_audit(
            records,
            audit_mode=mode,
            explain_with_llm=use_llm,
        )

    st.session_state.audit_result = result
    st.session_state.current_df = df.copy()
    st.session_state.file_name = filename
    st.session_state.agent_logs = result.get("logs", [])


def get_result_items():
    result = st.session_state.audit_result or {}
    return result.get("items", [])


def safe_text(value):
    return html.escape(str(value if value is not None else ""))


def find_amount_column(df):
    """Find a likely expense amount column without changing the source data."""
    if df is None or df.empty:
        return None

    exact_names = [
        "amount",
        "total",
        "total_amount",
        "final_total",
        "grand_total",
        "claimed_amount",
        "expense_amount",
        "bill_total",
        "receipt_total",
        "final_amount",
        "payable_amount",
        "total_payable",
    ]

    normalized = {
        str(column).strip().lower().replace(" ", "_"): column
        for column in df.columns
    }

    for name in exact_names:
        if name in normalized:
            return normalized[name]

    for column in df.columns:
        name = str(column).strip().lower()
        if (
            "amount" in name
            or "grand_total" in name
            or "final_total" in name
            or "bill_total" in name
            or "payable" in name
        ):
            return column

    return None


def get_numeric_amounts(df, amount_column):
    """Convert a likely amount column into numeric values for display."""
    if df is None or amount_column is None or amount_column not in df.columns:
        return pd.Series(dtype="float64")

    values = (
        df[amount_column]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("Rs.", "", regex=False)
        .str.replace("INR", "", regex=False)
        .str.strip()
    )

    return pd.to_numeric(values, errors="coerce").dropna()


def show_dashboard_table(df, title="Expense Records"):
    """Render records in a consistent dashboard section."""
    if df is None or df.empty:
        st.info("No expense records are available to display.")
        return

    st.markdown(f"#### 📄 {title}")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# HEADER
# ============================================================

st.markdown("""
<div class="eg-header">
    <div style="display:flex;justify-content:space-between;
                align-items:center;flex-wrap:wrap;gap:12px;">
        <div>
            <h1>🛡️ ExpenseGuard AI</h1>
            <p>MCP-Powered Workplace Expense Report Checker with
            Explainable AI & Local LLM Inference</p>
        </div>
        <div>
            <span class="eg-badge">⚡ Official Python MCP SDK</span>
            <span class="eg-badge">🦙 Ollama Llama 3.2</span>
            <span class="eg-badge">🔍 Explainable AI (XAI)</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# SIDEBAR CONTROLS
# ============================================================

with st.sidebar:
    st.markdown("### ⚙️ Audit Controls")

    audit_mode = st.selectbox(
        "Audit Scope / Intent",
        [
            "Comprehensive Full Audit",
            "Duplicate Scan Only",
            "Receipts Verification Only",
            "Policy Limits Check",
        ],
        help="Select which validation workflow the AI agent should use.",
    )

    mode_map = {
        "Comprehensive Full Audit": "full",
        "Duplicate Scan Only": "duplicate",
        "Receipts Verification Only": "receipt",
        "Policy Limits Check": "limit",
    }

    selected_mode = mode_map[audit_mode]

    use_llm = st.toggle(
        "🧠 Deep AI Explanations (Ollama)",
        value=True,
        help="Use the local Ollama model to explain audit findings.",
    )

    st.divider()

    st.markdown("### ⚡ Quick Demo Loaders")
    st.caption("Load sample corporate expense reports.")

    col_a, col_b = st.columns(2)

    sample_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "sample_data",
    )

    flagged_path = os.path.join(
        sample_dir, "sample_expenses_flagged.csv"
    )
    clean_path = os.path.join(
        sample_dir, "sample_expenses_clean.csv"
    )

    with col_a:
        if st.button("🚨 Flagged Report", use_container_width=True):
            if os.path.exists(flagged_path):
                sample_df = pd.read_csv(flagged_path)
                st.session_state.current_df = sample_df.copy()
                execute_audit(
                    sample_df,
                    "sample_expenses_flagged.csv",
                    selected_mode,
                    use_llm,
                )
                st.rerun()
            else:
                st.warning("Flagged sample CSV was not found in sample_data.")

    with col_b:
        if st.button("✅ Clean Report", use_container_width=True):
            if os.path.exists(clean_path):
                sample_df = pd.read_csv(clean_path)
                st.session_state.current_df = sample_df.copy()
                execute_audit(
                    sample_df,
                    "sample_expenses_clean.csv",
                    selected_mode,
                    use_llm,
                )
                st.rerun()
            else:
                st.warning("Clean sample CSV was not found in sample_data.")

    st.divider()

    st.markdown("### 🔌 MCP Tool Protocol Status")

    try:
        mcp_client = SyncMCPExpenseClient()
        available_tools = mcp_client.discover_tools()
        st.success("MCP Server Online")
        st.caption(
            f"Official Python MCP SDK · {len(available_tools)} tools registered"
        )

        with st.expander("🛠️ View Active MCP Tools"):
            for tool in available_tools:
                st.markdown(f"**{tool.get('name', 'Unknown tool')}**")
                st.caption(tool.get("description", ""))

    except Exception as exc:
        st.warning(f"MCP status unavailable: {exc}")

    st.divider()

    st.markdown("### 🦙 Ollama Local Status")

    try:
        ollama = OllamaClient(
            base_url=st.session_state.config.ollama_base_url,
            model=st.session_state.config.ollama_model,
        )
        online, status_message, models = ollama.check_health()

        if online:
            st.success(
                f"Online: {st.session_state.config.ollama_model} ready"
            )
        else:
            st.warning(f"Offline / fallback active: {status_message}")

    except Exception as exc:
        st.warning(f"Could not check Ollama: {exc}")

    st.divider()
    st.caption("ExpenseGuard AI · Local processing · MCP validation")


# ============================================================
# MAIN NAVIGATION
# ============================================================

tab_dash, tab_upload, tab_results, tab_xai, tab_settings = st.tabs([
    "📊 Dashboard",
    "📁 Upload Expenses",
    "🔍 Review Results",
    "🧠 AI Explanations (XAI)",
    "⚙️ Settings & Policies",
])


# ============================================================
# TAB 1: DASHBOARD
# ============================================================

with tab_dash:
    st.markdown("### 📊 Expense Compliance Dashboard")

    result = st.session_state.audit_result
    current_df = st.session_state.current_df

    # --------------------------------------------------------
    # DASHBOARD BEFORE AN AUDIT
    # Show extracted records immediately instead of an empty
    # dashboard after document extraction.
    # --------------------------------------------------------

    if not result:
        if current_df is not None and not current_df.empty:
            amount_column = find_amount_column(current_df)
            numeric_amounts = get_numeric_amounts(
                current_df,
                amount_column,
            )

            total_amount = (
                numeric_amounts.sum()
                if not numeric_amounts.empty
                else None
            )

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "Transactions Extracted",
                f"{len(current_df):,}",
            )

            c2.metric(
                "Total Extracted Amount",
                money(total_amount) if total_amount is not None else "—",
            )

            c3.metric(
                "Audit Status",
                "Pending",
            )

            c4.metric(
                "Documents Loaded",
                st.session_state.file_name or "Uploaded",
            )

            st.markdown("""
            <div class="eg-section">
                <div class="eg-section-title">📥 Extraction Preview</div>
                <div class="eg-section-subtitle">
                    These records have been extracted. Review them in the
                    Upload Expenses tab and run the audit to calculate
                    compliance statistics.
                </div>
            </div>
            """, unsafe_allow_html=True)

            show_dashboard_table(
                current_df,
                "Extracted Expense Records",
            )

            if amount_column and not numeric_amounts.empty:
                st.caption(
                    f"Amount total is calculated from the detected column: "
                    f"`{amount_column}`. Check the extracted records before auditing."
                )

            st.info(
                "Your records are loaded, but compliance results are not "
                "available until you run the audit."
            )

        else:
            c1, c2, c3, c4 = st.columns(4)

            c1.metric("Transactions Reviewed", "0")
            c2.metric("Passed", "0")
            c3.metric("Flagged", "0")
            c4.metric("Compliance Rate", "—")

            st.markdown("""
            <div class="eg-section">
                <div class="eg-section-title">Welcome to ExpenseGuard AI</div>
                <div class="eg-section-subtitle">
                    Upload receipts, invoices, PDFs, or expense spreadsheets
                    to begin. Extracted data appears here before the audit.
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.info(
                "Upload an expense report or use a Quick Demo Loader "
                "to view dashboard statistics."
            )

    # --------------------------------------------------------
    # DASHBOARD AFTER AN AUDIT
    # --------------------------------------------------------

    else:
        summary = result.get("summary", {})
        items = get_result_items()
        flagged_items = result.get("flagged_items", [])

        total_records = summary.get(
            "total_records",
            len(items),
        )

        passed_count = summary.get(
            "passing_count",
            max(total_records - len(flagged_items), 0),
        )

        flagged_count = summary.get(
            "flagged_count",
            len(flagged_items),
        )

        compliance_rate = summary.get("compliance_rate", 0)

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Transactions Reviewed",
            f"{total_records:,}",
        )

        c2.metric(
            "Passed",
            f"{passed_count:,}",
        )

        c3.metric(
            "Flagged",
            f"{flagged_count:,}",
            delta=(
                f"{flagged_count} require review"
                if flagged_count
                else "No flagged transactions"
            ),
            delta_color="inverse" if flagged_count else "normal",
        )

        c4.metric(
            "Compliance Rate",
            f"{compliance_rate:.1f}%",
        )

        st.markdown("""
        <div class="eg-section">
            <div class="eg-section-title">📋 Latest Audit Overview</div>
            <div class="eg-section-subtitle">
                Summary of the latest expense report processed by ExpenseGuard AI.
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.write(
            f"**Report:** {st.session_state.file_name or 'Uploaded report'}"
        )

        if items:
            result_df = pd.DataFrame(items)

            st.markdown("#### 📄 Audited Transactions")

            st.dataframe(
                result_df,
                use_container_width=True,
                hide_index=True,
            )

            # Transaction status distribution.
            if "status" in result_df.columns:
                status_counts = (
                    result_df["status"]
                    .fillna("Unknown")
                    .astype(str)
                    .value_counts()
                )

                if not status_counts.empty:
                    chart_col, details_col = st.columns([3, 2])

                    with chart_col:
                        st.markdown("#### 📊 Transaction Status")
                        st.bar_chart(status_counts)

                    with details_col:
                        st.markdown("#### 📌 Status Breakdown")
                        status_df = status_counts.rename_axis(
                            "Status"
                        ).reset_index(name="Transactions")

                        st.dataframe(
                            status_df,
                            use_container_width=True,
                            hide_index=True,
                        )

            # Expense category breakdown.
            if "category" in result_df.columns:
                amount_column = find_amount_column(result_df)

                if amount_column:
                    chart_data = result_df[
                        ["category", amount_column]
                    ].copy()

                    chart_data[amount_column] = pd.to_numeric(
                        chart_data[amount_column]
                        .astype(str)
                        .str.replace(",", "", regex=False)
                        .str.replace("₹", "", regex=False)
                        .str.replace("$", "", regex=False),
                        errors="coerce",
                    )

                    chart_data = chart_data.dropna(
                        subset=[amount_column]
                    )

                    if not chart_data.empty:
                        category_totals = (
                            chart_data.groupby("category")[amount_column]
                            .sum()
                            .sort_values(ascending=False)
                        )

                        st.markdown("#### 💼 Spending by Category")
                        st.bar_chart(category_totals)

            st.markdown("#### 🚩 Flagged Transactions")

            if flagged_items:
                st.dataframe(
                    pd.DataFrame(flagged_items),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("No flagged transactions were returned.")

        else:
            st.info("The audit did not return transaction items.")

    # --------------------------------------------------------
    # POLICY LIMITS
    # --------------------------------------------------------

    st.markdown("#### 💼 Current Office Expense Limits")

    cfg = st.session_state.config

    policy_df = pd.DataFrame([
        {
            "Expense Category": category,
            "Maximum Allowed": money(limit),
        }
        for category, limit in cfg.category_limits.items()
    ])

    st.dataframe(
        policy_df,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# TAB 2: UPLOAD EXPENSES
# ============================================================

with tab_upload:
    st.markdown("### 📁 Upload Expense Documents & Screenshots")

    st.write(
        "Upload expense reports, invoices, bills, PDFs, spreadsheets, "
        "or receipt screenshots."
    )

    uploaded_files = st.file_uploader(
        "Select one or multiple documents",
        type=[
            "pdf", "csv", "xlsx", "xls", "docx",
            "json", "txt", "png", "jpg", "jpeg",
            "webp", "bmp", "tif", "tiff",
        ],
        accept_multiple_files=True,
        key="expense_upload",
    )

    if uploaded_files:
        st.caption(
            "Selected files: " +
            ", ".join(file.name for file in uploaded_files)
        )

        # Detect changes in the selected upload batch.
        signature_builder = hashlib.sha256()

        for file in uploaded_files:
            signature_builder.update(file.name.encode("utf-8"))
            signature_builder.update(file.getvalue())

        signature = signature_builder.hexdigest()

        if st.session_state.upload_signature != signature:
            st.session_state.upload_signature = signature
            st.session_state.audit_result = None
            st.session_state.current_df = None
            st.session_state.file_name = None
            st.session_state.agent_logs = []

        image_files = [
            file for file in uploaded_files
            if os.path.splitext(file.name)[1].lower()
            in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"]
        ]

        if image_files:
            with st.expander(
                f"🖼️ View Uploaded Receipt Screenshots ({len(image_files)})",
                expanded=True,
            ):
                image_cols = st.columns(min(3, len(image_files)))

                for index, image_file in enumerate(image_files):
                    try:
                        image_cols[index % len(image_cols)].image(
                            image_file,
                            caption=image_file.name,
                            use_container_width=True,
                        )
                    except Exception:
                        pass

        if st.button(
            "📥 Extract Expense Records",
            type="primary",
            use_container_width=True,
        ):
            try:
                with st.spinner(
                    "Reading the newly selected documents independently..."
                ):
                    for file in uploaded_files:
                        file.seek(0)

                    extracted_df = load_documents_batch(uploaded_files)

                if extracted_df is None or extracted_df.empty:
                    st.warning(
                        "No expense records were extracted. "
                        "Check the document or receipt quality."
                    )
                else:
                    st.session_state.current_df = extracted_df.copy()
                    st.session_state.audit_result = None
                    st.session_state.file_name = (
                        uploaded_files[0].name
                        if len(uploaded_files) == 1
                        else f"Batch_{len(uploaded_files)}_Documents"
                    )

                    st.success(
                        f"Successfully parsed {len(uploaded_files)} file(s) "
                        f"into {len(extracted_df)} transaction record(s)."
                    )

                    st.info(
                        "Your extracted records are now available on the "
                        "Dashboard. Review them below before running the audit."
                    )

            except Exception as exc:
                st.error(f"Could not extract the documents: {exc}")

        current_df = st.session_state.current_df

        if current_df is not None and not current_df.empty:
            st.markdown("#### 📄 Extracted Expense Records")

            st.caption(
                "Review the extracted values before running the audit. "
                "Verify the printed final payable total on each receipt."
            )

            edited_df = st.data_editor(
                current_df,
                use_container_width=True,
                num_rows="dynamic",
                key=f"expense_editor_{st.session_state.upload_signature}",
            )

            if st.button(
                "🚀 Run ExpenseGuard AI Audit",
                type="primary",
                use_container_width=True,
            ):
                filename = (
                    uploaded_files[0].name
                    if len(uploaded_files) == 1
                    else f"Batch_{len(uploaded_files)}_Documents"
                )

                try:
                    execute_audit(
                        edited_df,
                        filename,
                        selected_mode,
                        use_llm,
                    )

                    st.success(
                        "Audit complete! Open Dashboard, Review Results, "
                        "and AI Explanations."
                    )

                except Exception as exc:
                    st.error(f"Audit failed: {exc}")
                    st.exception(exc)

    else:
        st.info("Choose one or more receipts or expense documents to begin.")

        # Retain access to previously extracted records when the uploader
        # is cleared, so the user can still review the current session data.
        current_df = st.session_state.current_df

        if current_df is not None and not current_df.empty:
            st.markdown("#### 📄 Previously Extracted Records")

            st.dataframe(
                current_df,
                use_container_width=True,
                hide_index=True,
            )

    with st.expander("ℹ️ Supported file types and extraction"):
        st.markdown("""
        - **Images:** PNG, JPG, JPEG, WEBP, BMP, TIFF
        - **PDF:** invoices, bills, expense statements and receipts
        - **Spreadsheets:** CSV and Excel
        - **Documents:** DOCX, TXT and JSON

        Receipt amounts come from the document extraction logic in
        `doc_loader.py`. The reader should use the printed final total;
        it should not add tax or sum line items to invent a total.
        """)


# ============================================================
# TAB 3: REVIEW RESULTS
# ============================================================

with tab_results:
    st.markdown("### 🔍 Expense Audit Results")

    result = st.session_state.audit_result

    if not result:
        st.info(
            "No audit results yet. Upload an expense report and run the audit, "
            "or use one of the Quick Demo Loaders."
        )

    else:
        items = result.get("items", [])
        flagged_items = result.get("flagged_items", [])

        st.markdown("#### 🔎 Filter Transactions")

        if items:
            result_df = pd.DataFrame(items)

            f1, f2 = st.columns(2)

            with f1:
                status_values = ["All"]

                if "status" in result_df.columns:
                    status_values += sorted(
                        result_df["status"].dropna().astype(str).unique().tolist()
                    )

                status_filter = st.selectbox(
                    "Status",
                    status_values,
                )

            with f2:
                categories = ["All"]

                if "category" in result_df.columns:
                    categories += sorted(
                        result_df["category"].dropna().astype(str).unique().tolist()
                    )

                category_filter = st.selectbox(
                    "Expense Category",
                    categories,
                )

            filtered_df = result_df.copy()

            if status_filter != "All" and "status" in filtered_df.columns:
                filtered_df = filtered_df[
                    filtered_df["status"].astype(str) == status_filter
                ]

            if category_filter != "All" and "category" in filtered_df.columns:
                filtered_df = filtered_df[
                    filtered_df["category"].astype(str) == category_filter
                ]

            st.dataframe(
                filtered_df,
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                f"Showing {len(filtered_df)} of {len(result_df)} transactions."
            )

        else:
            st.info("The audit did not return transaction items.")

        st.markdown("#### 🚩 Flagged Transactions")

        if flagged_items:
            st.dataframe(
                pd.DataFrame(flagged_items),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success("No flagged transactions were returned.")

        st.markdown("#### 📥 Export Audit Report")

        export_col1, export_col2 = st.columns(2)

        with export_col1:
            try:
                excel_bytes = generate_excel_report(
                    result.get("summary", {}),
                    items,
                    st.session_state.config,
                )

                st.download_button(
                    "⬇️ Download Excel Audit",
                    data=excel_bytes,
                    file_name="expenseguard_audit.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    use_container_width=True,
                )

            except Exception as exc:
                st.warning(f"Excel report could not be generated: {exc}")

        with export_col2:
            try:
                csv_output = generate_csv_report(items)

                if isinstance(csv_output, bytes):
                    csv_output = csv_output.decode("utf-8", errors="replace")

                st.download_button(
                    "⬇️ Download CSV Results",
                    data=csv_output,
                    file_name="expenseguard_audit.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            except Exception as exc:
                st.warning(f"CSV report could not be generated: {exc}")


# ============================================================
# TAB 4: EXPLAINABLE AI
# ============================================================

with tab_xai:
    st.markdown("### 🧠 AI Explanations (Explainable AI / XAI)")

    st.write(
        "Review why an expense was flagged, which rule was triggered, "
        "what evidence was found, and what action is recommended."
    )

    result = st.session_state.audit_result

    if not result:
        st.info("Run an expense audit to see the explanations.")

    else:
        flagged_items = result.get("flagged_items", [])

        if not flagged_items:
            st.success(
                "🎉 No flagged transactions were returned by the audit."
            )

        else:
            for index, item in enumerate(flagged_items, start=1):
                transaction_id = item.get("transaction_id", "Unknown")
                employee_id = item.get("employee_id", "Unknown")
                category = item.get("category", "Unknown")
                amount = item.get("amount", 0)
                status = item.get("status", "Needs Review")
                rule = item.get("rule_triggered", "No rule description")
                evidence = item.get("evidence", "No evidence supplied")
                explanation = item.get(
                    "plain_explanation",
                    "No explanation supplied.",
                )
                action = item.get(
                    "recommended_action",
                    "Review this expense manually.",
                )
                source = item.get("explanation_source", "deterministic")

                with st.container(border=True):
                    st.markdown(
                        f"#### 🚩 {index}. Transaction {safe_text(transaction_id)}"
                    )

                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Employee:** {employee_id}")
                    c2.write(f"**Category:** {category}")
                    c3.write(f"**Amount:** {money(amount)}")

                    st.warning(f"**Status:** {status}")
                    st.markdown("**Policy rule triggered**")
                    st.write(rule)

                    st.markdown("**Supporting evidence**")
                    st.code(str(evidence))

                    st.markdown("**Explanation**")
                    st.write(explanation)

                    st.info(f"**Recommended action:** {action}")
                    st.caption(f"Explanation source: {source}")


# ============================================================
# TAB 5: SETTINGS & POLICIES
# ============================================================

with tab_settings:
    st.markdown("### ⚙️ Settings & Office Policies")

    st.write(
        "Configure the maximum reimbursable amount for each expense category. "
        "Saved limits are used by subsequent audits."
    )

    cfg = st.session_state.config

    with st.form("settings_form"):
        st.markdown("#### 💼 Category Spending Caps (₹)")

        current_limits = cfg.category_limits

        category_defaults = {
            "Meals": 1500.0,
            "Travel": 10000.0,
            "Lodging": 15000.0,
            "Software": 8000.0,
            "Office Supplies": 3000.0,
            "Entertainment": 2500.0,
        }

        updated_limits = {}

        for category, default_limit in category_defaults.items():
            current_value = float(
                current_limits.get(category, default_limit)
            )

            updated_limits[category] = st.number_input(
                f"{category} Limit (₹)",
                min_value=0.0,
                max_value=10000000.0,
                value=current_value,
                step=500.0,
                key=f"policy_{category}",
            )

        # Keep any additional categories that already exist in config.
        for category, value in current_limits.items():
            if category not in updated_limits:
                updated_limits[category] = float(value)

        st.markdown("#### 🧾 Receipt & Reconciliation Rules")

        receipt_threshold = st.number_input(
            "Receipt Required Threshold (₹)",
            min_value=0.0,
            max_value=10000000.0,
            value=float(cfg.receipt_threshold),
            step=100.0,
        )

        claimed_total = st.number_input(
            "Claimed Report Total for Reconciliation (₹)",
            min_value=0.0,
            max_value=100000000.0,
            value=float(cfg.claimed_total),
            step=100.0,
            help="Use 0 when no separate claimed report total is available.",
        )

        st.markdown("#### 🦙 Ollama Model Configuration")

        ollama_url = st.text_input(
            "Ollama Base URL",
            value=cfg.ollama_base_url,
        )

        ollama_model = st.text_input(
            "Ollama Model Name",
            value=cfg.ollama_model,
        )

        ollama_timeout = st.number_input(
            "LLM Request Timeout (seconds)",
            min_value=5,
            max_value=120,
            value=int(cfg.ollama_timeout),
        )

        save_settings = st.form_submit_button(
            "💾 Save Policy Settings",
            type="primary",
            use_container_width=True,
        )

        if save_settings:
            cfg.category_limits.update(updated_limits)
            cfg.receipt_threshold = receipt_threshold
            cfg.claimed_total = claimed_total
            cfg.ollama_base_url = ollama_url
            cfg.ollama_model = ollama_model
            cfg.ollama_timeout = ollama_timeout

            st.session_state.config = cfg

            st.success(
                "Settings saved for this running session. "
                "Run the audit again to apply the updated limits."
            )

    st.divider()

    st.markdown("#### 📋 Current Policy Limits")

    current_policy_df = pd.DataFrame([
        {
            "Category": category,
            "Maximum Allowed": money(limit),
        }
        for category, limit in cfg.category_limits.items()
    ])

    st.dataframe(
        current_policy_df,
        use_container_width=True,
        hide_index=True,
    )

    st.metric(
        "Receipt Required Threshold",
        money(cfg.receipt_threshold),
    )

    st.caption(
        "These are fixed monetary caps. If your organization uses percentage "
        "limits, define those rules separately in the validation logic."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.markdown("""
<div class="eg-footer">
    ExpenseGuard AI · Local LLM inference · MCP-powered validation ·
    Explainable AI · Human review recommended before reimbursement approval
</div>
""", unsafe_allow_html=True)