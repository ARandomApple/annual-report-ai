"""
app.py — Streamlit application for Annual Report Intelligence.

Upload a company's annual report PDF and receive:
  - PDF metadata and text extraction (Chinese + English)
  - Automatic language detection
  - Scanned-PDF warning
  - (Future) Extracted financial data and key metrics
  - (Future) Anomaly detection signals
  - (Future) AI-powered economic interpretation
"""

import streamlit as st

from pdf_parser import parse_pdf

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Annual Report Intelligence",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("📊 Annual Report Intelligence")
st.sidebar.markdown(
    "Upload a company's annual report (PDF) in **Chinese or English** "
    "to extract and analyze its financial data."
)

# --- Output language selector (for future AI analysis) ---------------------
st.sidebar.markdown("---")
st.sidebar.markdown("### 🌐 Output Language")
output_language = st.sidebar.selectbox(
    label="Language for AI analysis output",
    options=["en", "zh"],
    format_func=lambda x: "English" if x == "en" else "中文",
    help="Future AI interpretations will be generated in this language.",
)
st.sidebar.caption("The report text itself is never translated.")

# --- Coming soon -----------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔜 Coming Soon")
st.sidebar.markdown(
    "- Financial data extraction\n"
    "- Key metric calculations\n"
    "- Anomaly / hidden signal detection\n"
    "- AI economic interpretation"
)

st.sidebar.markdown("---")
st.sidebar.caption("Phase 1 — Project Foundation")

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
st.title("📊 Annual Report Intelligence")
st.markdown(
    "Upload an annual report PDF (Chinese or English) to begin. "
    "This MVP extracts the PDF text and displays basic document "
    "information. Full financial analysis and AI interpretation "
    "are coming in the next phase."
)

# --- File uploader ----------------------------------------------------------
uploaded_file = st.file_uploader(
    "Upload Annual Report (PDF)  ",
    type=["pdf"],
    help="Select a company annual report in PDF format. Chinese and English reports are both supported.",
)

if uploaded_file is None:
    st.info("👆 Upload a PDF file to get started.")
    st.stop()

# --- Parse the PDF ----------------------------------------------------------
with st.spinner("Extracting text from PDF…"):
    try:
        pdf_doc = parse_pdf(
            file_bytes=uploaded_file.read(),
            file_name=uploaded_file.name,
        )
    except Exception as exc:
        st.error(f"Failed to parse PDF: {exc}")
        st.stop()

# --- Scanned PDF warning ----------------------------------------------------
if pdf_doc.scanned_warning:
    st.warning(pdf_doc.scanned_warning)

# --- Document overview ------------------------------------------------------
st.header("📄 Document Overview")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("File Name", pdf_doc.file_name)
col2.metric("Pages", pdf_doc.page_count)
col3.metric("File Size", f"{pdf_doc.file_size_kb} KB")
col4.metric("Text Length", f"{len(pdf_doc.full_text):,} chars")
col5.metric("Chars / Page", f"{pdf_doc.chars_per_page}")

# --- Language detection -----------------------------------------------------
st.header("🌐 Language Detection")

LANGUAGE_LABELS = {"zh": "中文 (Chinese)", "en": "English", "unknown": "Unknown"}
confidence_pct = f"{pdf_doc.language_confidence * 100:.0f}%"

if pdf_doc.language == "zh":
    st.success(
        f"Detected language: **{LANGUAGE_LABELS[pdf_doc.language]}** "
        f"({confidence_pct} confidence)"
    )
elif pdf_doc.language == "en":
    st.success(
        f"Detected language: **{LANGUAGE_LABELS[pdf_doc.language]}** "
        f"({confidence_pct} confidence)"
    )
else:
    st.info(
        "Could not reliably detect the document language. "
        "The PDF may contain very little extractable text."
    )

# --- Metadata ---------------------------------------------------------------
if pdf_doc.metadata:
    with st.expander("📋 PDF Metadata"):
        st.json(pdf_doc.metadata)

# --- Text preview -----------------------------------------------------------
st.header("🔍 Text Preview")
st.caption(
    f"Showing the first {len(pdf_doc.text_preview):,} characters "
    f"from {len(pdf_doc.full_text):,} total. "
    "Original text is preserved — no translation is applied."
)
st.text_area(
    label="Extracted text preview",
    value=pdf_doc.text_preview,
    height=400,
    disabled=True,
    label_visibility="collapsed",
)

# --- Status badges ----------------------------------------------------------
st.header("⚙️ Pipeline Status")

status_col1, status_col2, status_col3, status_col4 = st.columns(4)
status_col1.success("✅ PDF Parsing")
status_col2.info("⏳ Financial Extraction")
status_col3.info("⏳ Signal Detection")
status_col4.info("⏳ AI Interpretation")

st.caption(
    "Phase 1 is complete. PDF parsing, language detection, and "
    "text extraction are functional. Financial extraction, signal "
    "detection, and AI interpretation will be implemented in future phases."
)
