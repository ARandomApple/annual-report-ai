# 📊 Annual Report Intelligence

Upload a company's annual report (PDF) and receive AI-powered financial analysis.

**Phase 1** — Project foundation with PDF upload and text extraction.

## Architecture

```
PDF Annual Report
  → PDF Parser (PyMuPDF)
  → Structured Financial Data (pandas)
  → Financial Analysis & Signal Detection (Python)
  → Economic Interpretation (DeepSeek LLM)
  → Streamlit Report
```

**Design principle:** Python handles numbers. The LLM handles interpretation.
Calculations are never delegated to the AI.

## Tech Stack

| Component          | Library                  |
| ------------------ | ------------------------ |
| UI                 | Streamlit                |
| PDF Parsing        | PyMuPDF (fitz)           |
| Data Processing    | pandas, numpy            |
| Visualization      | Plotly                   |
| LLM                | DeepSeek (OpenAI SDK)    |
| Config             | python-dotenv            |

## Setup

### 1. Create a virtual environment (recommended)

```bash
cd annual-report-ai
python -m venv venv

# Activate on macOS / Linux:
source venv/bin/activate

# Activate on Windows:
venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API credentials

```bash
cp .env.example .env
```

Edit `.env` and add your DeepSeek API key:

```
DEEPSEEK_API_KEY=sk-your-actual-key
```

### 4. Run the application

```bash
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

## Project Structure

```
annual-report-ai/
├── app.py               # Streamlit application entry point
├── pdf_parser.py         # PDF text and metadata extraction (PyMuPDF)
├── financial_engine.py   # Financial metrics & signal detection (placeholder)
├── ai_analyst.py         # DeepSeek economic interpretation (placeholder)
├── requirements.txt      # Python dependencies
├── .env.example          # API key configuration template
└── README.md             # This file
```

## Current Status (Phase 1)

- [x] Streamlit app with PDF uploader
- [x] PDF text extraction via PyMuPDF
- [x] Document metadata display
- [x] Text preview viewer
- [ ] Financial data extraction from PDF text
- [ ] Metric calculations (margins, growth rates, ratios)
- [ ] Signal detection (revenue quality, margin pressure, etc.)
- [ ] DeepSeek economic interpretation

## Planned Metrics & Signals

### Key Metrics

Revenue growth, profit growth, gross margin, operating margin, net margin,
free cash flow margin, ROA, ROE, debt-to-equity, inventory growth,
receivables growth.

### Anomaly Signals

- Revenue ↑ but Inventory ↑↑ → possible inventory accumulation
- Revenue ↑ but Receivables ↑↑ → possible revenue quality deterioration
- Profit ↑ but Operating Cash Flow ↓ → possible earnings quality deterioration
- Revenue ↑ but Operating Margin ↓ → margin pressure
- Debt ↑ and Interest Expense ↑ → increasing financing pressure
- CapEx ↑↑ → investigate expansion vs. capital requirements

### Line Items Tracked

Revenue, gross profit, operating profit, net income, operating cash flow,
free cash flow, cash, debt, inventory, accounts receivable.

## License

This is an MVP project. Use at your own discretion.
