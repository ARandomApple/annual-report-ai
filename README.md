# 📊 Annual Report Intelligence

Upload a company's annual report (PDF) and receive AI-powered financial analysis.

**Current checkpoint — 2026-09-24:** Upload one or two PDFs, inspect financial statements, compare multiple years, compute deterministic metrics and review all-period accounting checks in Streamlit. On-demand GPT analysis is wired; configure an OpenAI API key to enable real requests.

**2026-09-25 update:** The interface now leads with colorful financial cards and interactive charts. Local OCR can recover Chinese and English text from scanned PDFs and PDFs with unreadable text layers. A locally available Xiaomi 2025 annual report has been checked end to end: PDF pages 270–273 and 278–279 produce 2025/2024 income, balance sheet, and cash-flow figures. OCR figures remain provisional until the original pages have been reviewed. ChatGPT Plus does not include OpenAI API usage; uploading, OCR, charts, comparison, and validations run without API charges.

**Interactive overview:** The first four cards remain revenue, net income, operating cash flow, and revenue growth. Scroll the card rail or use its arrows to choose among 15 indicators. Clicking a card shows the current and prior year's values, their difference, and a percentage change where the prior monetary value is positive; percentage indicators instead use percentage-point differences. Paired bars are used only for nonnegative values. A line chart appears only when at least three consecutive, fiscally compatible years are available. The decorative 3D model has been removed. Sources retain PDF pages, missing values are not treated as zero, and incompatible currencies are not combined. Money units adapt between yuan, ten-thousand yuan, and hundred-million yuan to avoid displaying small nonzero values as 0.00.

**Upload guidance and change drivers:** The upload view now shows its processing stages and actionable messages for unreadable PDFs, failed extraction, OCR results without statements, and missing or incompatible metrics. Raw extraction warnings remain available under recognition details. A change contribution chart appears only when source amounts reconcile. If two years of business-segment rows exactly sum to revenue, it shows each segment's contribution to the revenue change. Otherwise, when revenue and cost of revenue are compatible, it shows their contributions to the change in calculated gross profit; this is explicitly labelled as a different question. The chart uses zero as the baseline for the *change*, with full prior/current amounts displayed above it. No chart is shown when the required inputs conflict or are missing.

### Local OCR

For local development, run `python setup_ocr.py` once to install RapidOCR and the pinned PP-OCRv5 recognition model into ignored local folders. The cloud deployment instead uses `requirements.txt` and the bundled `models/` copy. The local setup downloads packages and a model; locally processed annual-report data stays on your computer. A cloud deployment processes uploaded files on its server. For a PDF whose text copies as gibberish, upload it, expand **文字识别与原图核对**, then click **识别财务报表**. The page field may be left empty for automatic discovery, or filled with PDF page ranges such as `270-273,278-279`. The 20-page limit prevents long full-report OCR runs. Check the page images beside the recognized text, particularly amounts, negative signs, years, and units. GPT analysis remains unavailable until you confirm that review. The original PDF is not rewritten.

If `http://127.0.0.1:8501/` refuses to connect after a computer restart or closing the terminal, run `streamlit run app.py` again. The app runs locally and stops when its server process stops.

## Public HTTPS deployment

The web app is prepared for Streamlit Community Cloud. Deploy `app.py` from a
GitHub repository, select Python 3.11 (the version used for local tests), and
choose a `streamlit.app` subdomain. Streamlit provides HTTPS. The root
`requirements.txt` installs Python packages; `packages.txt` supplies Linux
libraries needed by OCR. The pinned OCR recognition model is in `models/`.
Do not upload `.env`, PDFs, `ocr_runtime/`, or `.ocr_models/`.

Visitors do not need an account. Each visitor enters their own OpenAI API key
in the AI section; no shared key is used by the web UI. The key is held in
Streamlit session memory and used only when the visitor clicks Generate.
The PDF itself is processed on the hosting server, not on the visitor's
computer. The AI preview shows the extracted evidence that will be sent to
OpenAI. Do not upload confidential reports to a public hosted instance.
Community Cloud hosts apps in the United States and has variable resource
limits. The public app caps each PDF upload at 25 MB; concurrent OCR jobs may
still exceed the available capacity.

After deployment, pushing code to the same GitHub branch updates the app at
the same HTTPS URL. Dependency changes trigger a full rebuild. Streamlit
sessions may reset during updates, requiring visitors to enter their key again.

## Architecture

```
PDF Annual Report
  → PDF Parser (PyMuPDF)
  → Structured Financial Data (pandas)
  → Financial Analysis & Signal Detection (Python)
  → Economic Interpretation (OpenAI GPT, explicit button)
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
| LLM                | OpenAI Responses API    |
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

### 3. API configuration

No server-side API key is required for the web app. Each visitor enters their own
OpenAI API key in the GPT analysis section after uploading a report. The key is
held in that browser's Streamlit session and is not written to a file or database.
The server processes it while making the request; use HTTPS when deployed.
Without a visitor key, PDF extraction and financial calculations still work,
but the paid AI button stays disabled. The web UI never falls back to a key in
`.env` or the process environment.

Optionally, set `OPENAI_MODEL` in a project-local `.env` file to change the
model for the deployment. Do not put a shared `OPENAI_API_KEY` on a public server.

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
├── financial_engine.py   # Deterministic financial metrics; signals pending
├── ai_analyst.py         # On-demand GPT interpretation via Responses API
├── requirements.txt      # Python dependencies
├── packages.txt          # Linux libraries for hosted OCR
├── models/               # Pinned OCR recognition model
├── .env.example          # Optional model override
└── README.md             # This file
```

## Original Phase 1 Checklist (historical; see Step 2 update below)

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


## Phase 2 Step 2 — backend usage

`table_extractor.py` adds a deterministic backend, with no API key or LLM:

```python
from pathlib import Path
from table_extractor import extract_financial_report

path = Path("annual-report.pdf")
report = extract_financial_report(path.read_bytes(), path.name)
print(report.extraction_warnings)
for statement in (report.balance_sheet, report.income_statement,
                  report.cash_flow_statement):
    if statement:
        for metric in statement.metrics:
            for value in metric.values:
                print(metric.canonical_name, value.period.year,
                      value.normalized_value, value.source_page)
```

- Processes only detected statement ranges; tries PyMuPDF tables, physical word
  positions, then explicitly separated text rows.
- Reads explicit period columns, excludes note/change columns, preserves missing
  values, and records the raw label/value, page, extraction method and confidence.
- Detects currency/scale; unknown monetary scale yields `normalized_value=None`.
  Percentages and per-share values are not multiplied by the monetary scale.
- Separates consolidated and parent columns. Consolidated statements are preferred;
  parent statements remain in `alternative_statements`.
- Keeps conflicting duplicate rows and emits warnings; does not overwrite values.
- Uses exact aliases after removing row numbering and add/subtract prefixes.
  Other labels remain available with `canonical_name=None` for review.
- A structural adapter supports combined Chinese group/company headings and
  repeated adjacent statement titles without changing frozen Step 1 code.

### Verification (2026-09-23)

Step 1: 80 checks passed. Step 2: 30 unittest cases passed. Fixtures cover Chinese
and English, notes, reversed years, restatements, mixed scopes, units, missing
values, fallback methods and duplicate conflicts. Run from the project directory:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -B tests/test_financial_extractor_step1.py
python -B -m unittest discover -s tests -p test_table_extractor_step2.py -v
```

The local 219-page China Telecom report was also tested: balance sheet pages
85–86, income statement page 87 and cash-flow statement page 88 were detected;
consolidated and company columns were kept separate. Reference revenue, profit
attributable to parent and operating cash-flow amounts were verified separately
from production rules.

### Remaining work / limits

The Streamlit app displays extraction results and deterministic metrics. AI
interpretation is available after key setup; anomaly signal detection is still pending. OCR is not implemented. Ambiguous periods,
scopes and irregular row widths are skipped with warnings. Position fallback
requires at least two visible year headings; complex multi-line labels or merged
headers may require further layout support. Continuation header inheritance is
flagged for review. Unknown aliases are retained, not guessed. One real report
passing does not establish general accuracy across all report layouts.

The validation engine now checks every available balance-sheet period and keeps
consolidated/parent scopes and original/restated versions separate. The legacy
validate_balance_sheet_equation entry returns only the latest period; the UI uses
run_all_validations for all available periods in the selected scope.


## Web interface checkpoint — 2026-09-23

The existing Streamlit app now exposes extracted statements:

- Balance sheet, income statement and cash-flow tabs.
- Consolidated/parent/unknown scope selector, limited to scopes actually found.
- Original labels and reported values, currency, scale and PDF page numbers.
- Expandable provenance including normalized values, period, canonical mapping
  and extraction confidence; duplicate source rows remain visible.
- Source-page text for checking each statement, plus PDF metadata and preview.
- Explicit missing-data, malformed-PDF and extraction-failure states.
- Cached parsing/extraction (up to three files for one hour) for scope changes.

Run locally from the project directory in PowerShell:

```powershell
python -m streamlit run app.py
```

Additional UI tests:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -B -m unittest discover -s tests -p test_app.py -v
```

Verified with Streamlit 1.61.1: six UI/presentation tests pass, along with the
80 Step 1 checks and 30 Step 2 tests. A real 219-page China Telecom upload also
passed Streamlit AppTest: all three statements and provenance tables rendered;
switching scope changed 2025 revenue from the consolidated amount to the parent
amount correctly. AppTest verifies app execution and widget interactions; this
checkpoint does not include a browser screenshot/layout audit.

Later sections in this README record subsequent work.


## Financial metrics and validation — 2026-09-24

The selected scope now includes a metrics table with formulas, periods, units,
source pages, unavailable-result reasons and expandable input provenance.

| Metric | Definition |
| --- | --- |
| Revenue / net-income growth | (current − previous) / previous × 100%; consecutive annual periods, positive prior base |
| Net / operating margin | corresponding profit / revenue × 100% |
| Gross margin | (revenue − cost of revenue) / revenue × 100%; explicitly labeled definition |
| Debt to assets | total liabilities / total assets × 100%, same balance-sheet date |
| Operating cash-flow margin | operating cash flow / revenue × 100%, identical reporting period |
| Simplified free cash flow | operating cash flow − absolute capital expenditure |

`financial_inputs.py` centralizes compatible input selection. The engine blocks
unknown currency/scale/scope, missing values, nonfinite amounts, conflicting
duplicates, incompatible periods and currency mixing. Identical duplicate values
retain provenance. Original/restated comparative ambiguity blocks growth; quarter
and half-year values are not annualized. Cross-statement periods require exact
identity, so partially missing date metadata can conservatively suppress results.
There is no currency conversion. Monetary arithmetic uses Decimal over parsed
values; source extraction still uses the existing float-based model.

`validation_engine.py` now reports passed / failed / skipped separately. It checks
all balance-sheet periods and relevant input issues; no latest-period-only
shortcut is used by the UI. Rounding tolerance is the sum of half each operand's
reported decimal unit after scaling. A broad percentage-of-assets allowance is
not used. Values are never changed to force checks to pass. Coverage gaps and
unavailable checks remain visible. These checks are not a full audit; cash-flow
roll-forward, ROA/ROE, industry-specific adjustments and anomaly rules remain
future work. Computable metrics are not hidden when a separate accounting check
fails; the page displays the failed checks and a warning for review.

Verification: 28 finance tests, 30 Step 2 tests, 7 UI/presentation tests, plus all
80 original Step 1 checks pass. The real 219-page China Telecom report renders
through Streamlit AppTest with scope switching; both scopes' 2025 and 2024 balance
sheets reconcile at the reported cent precision. Example consolidated 2025 output:
net margin 6.341138%, debt/assets 46.216881%, simplified FCF CNY 51,370,731,839.33.
At the metrics checkpoint no GPT/API calls had been made. The local preview server was subsequently started on 127.0.0.1:8501.

Run all tests from the project directory:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -B -m unittest discover -s tests -p 'test_*.py'
```

The original Step 1 file executes 80 assertions during discovery; unittest's own
case count is 65 (30 extraction + 28 finance + 7 UI).


## GPT integration — 2026-09-24

The financial-data page now has a GPT section. PDF extraction and metric
calculations never call OpenAI. Only the explicit Generate AI Analysis button
sends a request. Each visitor must enter their own key in the web UI; a
server-side key cannot enable this button. The key is kept for the current
Streamlit session and is not persisted. OPENAI_MODEL defaults to gpt-5.4-mini;
access and charges belong to the visitor's API account. Never paste a key into
chat or commit it to source control.

Implementation uses the OpenAI Responses API and Pydantic Structured Outputs:
- Sends the selected scope's identified values, precomputed metrics, all relevant
  checks, extraction warnings and up to eight source-page excerpts (2,000 chars
  each). Does not upload the entire PDF. A preview displays the exact payload.
- Caps raw value entries at 160 and reports omissions. Payload size is capped at
  120,000 characters; output cap is 4,000 tokens. These are size limits, not a
  guaranteed currency spending cap. Token usage is displayed after completion.
- Explicit official API endpoint, 60-second request timeout, no automatic retries,
  store=False. This setting is not a promise of zero provider-side retention.
- Structured facts/inferences cite evidence IDs that are checked against the
  actual payload; incomplete/refused/invalid-reference output is rejected.
  Citation existence does not prove semantic correctness or numerical fidelity
  of generated prose. Human review is still required.
- Evidence is treated as untrusted source material in developer instructions;
  the model must not follow instructions embedded in PDF text or filenames.
- Results remain only in the current Streamlit session. A content/model/language
  fingerprint prevents showing another scope or document's result. Routine
  reruns do not call the API. Clear a saved result explicitly to generate again.
- Missing keys disable generation. Authentication, quota, connectivity, timeout,
  incomplete output and parsing failures get sanitized messages without exposing
  credentials or raw API responses. A timeout may already have incurred charges.

Verification: 16 new offline AI tests passed, including a real SDK parse through
httpx.MockTransport (no network). Full regression: 81 unittest cases plus the
80 original Step 1 checks passed. Real-report Streamlit flow was checked without
clicking the AI button. No real OpenAI request was sent; live quality, account
access and billing validation remain pending the user's key and explicit click.

Official references:
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/models/gpt-5.4-mini


## Two reports / three-year comparisons — 2026-09-24

Select 双年报 · 多年对比 in the app. Upload adjacent-year reports (in either order),
review their first-page text, confirm that they belong to the same company, then
choose consolidated or parent scope. Two reports may expose three years; actual
years come from extracted data and missing years are never fabricated.

The comparison table shows normalized values, source status, absolute annual
changes and growth percentages, plus both documents' raw values. Equal overlapping
values are deduplicated only for the displayed point, with both sources retained.
Currency, value type, scale, fiscal dates and restatement flags must be compatible.
No FX conversion is performed. Conflicts, missing values and incompatible periods
block affected changes and continuous charts. Original vs restated values are
preserved without automatically preferring the newer report. A negative/zero base
blocks conventional percentage growth, but an absolute change may be displayed.
Growth is currently limited to monetary line items; EPS and percentages are shown
as values without potentially misleading growth calculations.

Company identity is not reliably extracted, so explicit user confirmation is
required for each pair of file contents. Known conflicting company names are
rejected. The same PDF uploaded twice is rejected by content hash. Account policy
and financial classification changes may still need manual review even when values
match; this is not a claim of full economic comparability.

GPT comparison evidence includes document IDs, filenames, original page numbers,
overlap discrepancies, computed changes and per-document validation results. IDs
remain unambiguous when both reports cite the same page number. API calls remain
manual, with separate single-report/comparison session result keys and no automatic
requests or retries. Up to 180 comparison points (conflicts first), four excerpts
per file and 1,200 characters per excerpt are included; the total input-size cap
still applies. Omitted content is disclosed in the payload.

23 comparison tests pass: three-year assembly, reversed upload order, duplicate
content, company confirmation/mismatch, scope/currency/scale/period differences,
missing values, conflicts, raw provenance, document-specific AI references and the
full dual-upload app route. Together with prior checks this is 104 unittest cases
plus 80 original Step 1 assertions. Two-file tests use explicit fixtures, not a
second real-company PDF: only one real annual report is currently available locally.
No real OpenAI request was sent during implementation.
