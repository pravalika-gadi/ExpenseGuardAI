# ExpenseGuard AI — Professional Expense Verification System

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP SDK](https://img.shields.io/badge/Model_Context_Protocol-Official_Python_SDK_v2-purple.svg)](https://modelcontextprotocol.io/)
[![Ollama](https://img.shields.io/badge/Ollama-Llama_3.2_Local-black.svg)](https://ollama.ai/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-red.svg)](https://streamlit.io/)
[![Pytest](https://img.shields.io/badge/Tests-27%2F27_Passing-brightgreen.svg)](https://pytest.org/)

**ExpenseGuard AI** is a production-style, locally hosted expense verification system engineered for corporate finance and internal audit teams. It performs strict deterministic audit checks on employee expense submissions (identifying potential duplicate transactions, policy limit breaches, missing receipts, incomplete mandatory fields, and totals discrepancies), orchestrates verification tools through the **official Python Model Context Protocol (MCP) SDK**, and leverages a local **Llama 3.2** LLM via **Ollama** to provide grounded, explainable audit findings with actionable next steps for human finance reviewers.

---

## 1. System Architecture

```
 ┌──────────────────────┐         ┌────────────────────────┐         ┌──────────────────────────────┐
 │ Finance Auditor /    │ ──────> │ Streamlit Web UI       │ ──────> │ ExpenseAuditAgent            │
 │ Reviewer (Browser)   │         │ (Dashboard & Controls) │         │ (Goal-Driven Tool Planning)  │
 └──────────────────────┘         └────────────────────────┘         └──────────────────────────────┘
                                                                                    │
                                                                                    ▼
 ┌─────────────────────────┐         ┌───────────────────────┐         ┌──────────────────────────────┐
 │ Local MCP Server Process│ <────── │ Real MCP SDK Client   │ <────── │ SyncMCPExpenseClient         │
 │ (mcp_server.py)         │         │ (stdio_client)        │         │ (mcp_client.py)              │
 └─────────────────────────┘         └───────────────────────┘         └──────────────────────────────┘
              │
              ▼ (Deterministic Tool Invocations over stdio)
 ┌────────────────────────────────────────────────────────────────────────────────────────────┐
 │  1. read_expense_report       2. check_missing_fields     3. check_duplicate_expenses      │
 │  4. validate_expense_amounts  5. check_receipt_status     6. generate_expense_summary      │
 └────────────────────────────────────────────────────────────────────────────────────────────┘
              │
              ▼ (Factual Evidence & Math Results)
 ┌─────────────────────────┐         ┌───────────────────────┐         ┌──────────────────────────────┐
 │ Ollama Local LLM        │ <────── │ Explainable AI (XAI)  │ <────── │ Multi-Sheet Excel Dossier    │
 │ (Llama 3.2 3B Model)    │ ──────> │ Prompt Guardrails     │ ──────> │ & Audit Report Export        │
 └─────────────────────────┘         └───────────────────────┘         └──────────────────────────────┘
```

### Local Execution & Privacy Architecture
- **Zero Cloud Transmission**: All expense processing, file parsing, MCP tool execution, and LLM reasoning run 100% locally on your machine. Financial records are never transmitted to external services or cloud APIs.
- **Deterministic Math Primacy**: Calculations, policy checks, and duplicate detection use pure Python logic. The LLM is strictly used for natural language explanation and executive synthesis, preventing arithmetic hallucinations.
- **Offline Fault Tolerance**: If Ollama is offline or unavailable, the core system continues operating in deterministic fallback mode with full validation and report generation capabilities intact.

---

## 2. Core Capabilities

### Expense Report Management
- **Universal File Ingestion**: Ingests CSV and Excel (`.xlsx`, `.xls`) reports, with optional support for PDF statements, Word tables, JSON feeds, and receipt images via local OCR.
- **Interactive Verification**: Direct inline data editor allows finance reviewers to inspect and adjust extracted fields prior to final audit.
- **Search, Sort & Filter**: Filter transactions by validation status (`Passed`, `Needs Review`, `Invalid Data`), category, or text query (Transaction ID, Employee ID, or description).
- **Synthetic Sample Datasets**: Includes pre-configured flagged test reports and clean compliant reports with one-click sidebar loading.

### Deterministic Validation Engine
- **Mandatory Fields**: Validates non-empty `transaction_id`, `employee_id`, `date`, `category`, `description`, and `amount`.
- **Duplicate Detection**: Identifies exact duplicates (same employee, amount, date, description) and potential near-duplicates (same employee and amount within 2 calendar days).
- **Amount & Date Checks**: Flags negative or zero amounts, non-numeric formats, and future transaction dates.
- **Category Policy Caps**: Validates line-item amounts against departmental spending limits (e.g., Meals: ₹1,500, Travel: ₹10,000, Lodging: ₹15,000, Software: ₹8,000).
- **Receipt Compliance**: Enforces receipt verification for expenses equal to or exceeding configurable thresholds (default: ₹500).
- **Totals Reconciliation**: Reconciles the mathematical sum of line items against claimed report totals.

### Genuine Model Context Protocol (MCP) Integration
- Built with the **official Python MCP SDK (`mcp`)**.
- Local **MCP Server** (`mcp_server.py`) registers 6 validation tools with strict JSON schemas.
- Local **MCP Client** (`mcp_client.py`) discovers tools dynamically and executes invocations over standard input/output (`stdio`) transport.
- Logs are strictly routed to `stderr` to maintain clean, uncorrupted JSON-RPC communication frames.

### Explainable AI (XAI) & Human-in-the-Loop Review
- Every flagged transaction details:
  - **Transaction ID & Employee ID**
  - **Amount & Expense Category**
  - **Validation Status**: `Passed`, `Needs Review`, or `Invalid Data`
  - **Exact Validation Rule Triggered**
  - **Deterministic Supporting Evidence**
  - **Plain-Language Explanation**
  - **Recommended Next Action**
- **Non-Presumptive Standards**: The system never accuses employees of fraud or automatically approves/rejects reimbursements; final decisions remain with human finance reviewers.

---

## 3. Project File Structure

```
ExpenseGuardAI/
├── .gitignore                      # Git ignore patterns for private data & cache
├── .env.example                    # Optional environment variable template
├── README.md                       # Complete technical documentation & setup guide
├── requirements.txt                # Python package dependencies
├── run_app.bat                     # 1-click Windows startup script
├── app.py                          # Streamlit web application & dashboard
├── agent.py                        # AI Agent tool planning and review orchestration
├── mcp_server.py                   # Genuine MCP server exposing 6 validation tools
├── mcp_client.py                   # Genuine MCP stdio client using official MCP SDK
├── validators.py                   # Pure Python deterministic validation engine
├── llm.py                          # Local Ollama client with XAI prompt guardrails
├── config.py                       # Policy configuration, limits, and defaults
├── doc_loader.py                   # Universal document & screenshot loader
├── report_gen.py                   # Multi-sheet Excel (.xlsx) & CSV report generator
├── create_samples.py               # Synthetic test dataset generator
├── sample_data/                    # Pre-generated sample expense datasets
│   ├── sample_expenses_flagged.csv # Test report with deliberate policy violations
│   ├── sample_expenses_flagged.xlsx# Excel version of flagged test report
│   ├── sample_expenses_clean.csv   # 100% compliant test report
│   └── sample_expenses_clean.xlsx  # Excel version of clean test report
└── tests/                          # Automated Pytest test suite (27 tests)
    ├── test_validators.py          # Deterministic rules & parsing tests
    ├── test_mcp.py                 # Real MCP stdio discovery and invocation tests
    ├── test_agent.py               # Agent planning and workflow tests
    ├── test_llm.py                 # Ollama health check & prompt building tests
    ├── test_reports.py             # Multi-sheet Excel & CSV generation tests
    └── test_doc_loader.py          # Ingestion & file parsing tests
```

---

## 4. Local Windows Execution Guide

### Option 1: 1-Click Launch (Easiest)
Double-click **`run_app.bat`** in File Explorer, or run in PowerShell:
```powershell
.\run_app.bat
```
The script validates Python and Ollama, generates sample files if missing, and launches the web dashboard.

---

### Option 2: Step-by-Step Manual Setup

#### Step 1: Open PowerShell in Workspace
```powershell
cd c:\Users\Gadipravallika\Downloads\ExpenseGuardAI
```

#### Step 2: Verify Python Installation
Python 3.10+ is required:
```powershell
python --version
```

#### Step 3: Create & Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### Step 4: Install Dependencies
```powershell
pip install -r requirements.txt
```

#### Step 5: Install & Start Ollama (for Local AI Inference)
1. Download and install Ollama for Windows from [ollama.ai](https://ollama.ai/).
2. Verify Ollama CLI:
   ```powershell
   ollama --version
   ```
3. Start the Ollama background daemon if not already running:
   ```powershell
   ollama serve
   ```
4. In another terminal, pull the recommended model (Llama 3.2 3B, ~2.0 GB):
   ```powershell
   ollama pull llama3.2
   ```

*(Note: If Ollama is not installed or the model is not downloaded, ExpenseGuard AI will automatically operate in deterministic fallback mode).*

#### Step 6: Run Automated Tests
Execute the full automated test suite:
```powershell
python -m pytest -v
```
*(All 27 tests execute and pass in ~30s).*

#### Step 7: Launch the Application
Start the Streamlit application:
```powershell
python -m streamlit run app.py
```
Open your browser at:
👉 **`http://localhost:8501`**

---

## 5. Automated Test Suite

The test suite validates every layer of the system:

| Test Module | Coverage Area | Status |
| :--- | :--- | :---: |
| `tests/test_validators.py` | Missing fields, exact/near duplicates, category limits, negative amounts, future dates, receipt thresholds, totals reconciliation, record normalization | **10 Passed** |
| `tests/test_mcp.py` | Official MCP server tool registration, real stdio client tool discovery, stdio tool execution, file reading tool, error handling | **7 Passed** |
| `tests/test_agent.py` | Agent goal-driven tool planning (full, duplicate, receipt, limit), audit pipeline execution, execution logging | **2 Passed** |
| `tests/test_llm.py` | Ollama client health check, grounded XAI prompt building, response parsing, unreachable service fallback | **3 Passed** |
| `tests/test_reports.py` | Multi-sheet Excel workbook structure, formatting, sign-off block, CSV export generation | **2 Passed** |
| `tests/test_doc_loader.py` | JSON parsing, CSV ingestion, image receipt OCR parsing | **3 Passed** |
| **Total** | **Complete System Test Suite** | **27 Passed (100%)** |

---

## 6. Configuration & Environment Variables

Create a `.env` file (based on `.env.example`) to override default local settings:

```ini
# Ollama local inference server URL
OLLAMA_BASE_URL=http://localhost:11434

# Default local LLM model for explainable AI
OLLAMA_MODEL=llama3.2:latest

# Ollama request timeout in seconds
OLLAMA_TIMEOUT=20

# Streamlit web server settings
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=localhost
```

Category spending caps and receipt thresholds can also be customized dynamically at runtime through the **⚙️ Settings & Policies** tab in the web application.

---

## 7. License
Open-source under the MIT License.
