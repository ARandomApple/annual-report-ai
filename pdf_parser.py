"""
pdf_parser.py — Extract text and metadata from annual report PDFs.

Uses PyMuPDF for robust PDF text extraction.
Supports both Chinese and English reports with automatic language detection.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import pymupdf


# ---------------------------------------------------------------------------
# Character ranges for language detection
# ---------------------------------------------------------------------------

# Core CJK Unified Ideographs (Chinese characters)
_CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs (common)
    (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
]

# Full-width punctuation commonly found in Chinese text
_CJK_PUNCTUATION_RANGES = [
    (0x3000, 0x303F),   # CJK Symbols and Punctuation
    (0xFF00, 0xFF5F),   # Fullwidth Forms (full-width Latin, punctuation)
    (0xFFE0, 0xFFEF),   # Halfwidth and Fullwidth Forms
]


def _is_cjk_char(ch: str) -> bool:
    """Return True if the character is a CJK unified ideograph."""
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def _is_cjk_or_punct(ch: str) -> bool:
    """Return True if the character is a CJK ideograph or CJK punctuation."""
    cp = ord(ch)
    if any(lo <= cp <= hi for lo, hi in _CJK_RANGES):
        return True
    if any(lo <= cp <= hi for lo, hi in _CJK_PUNCTUATION_RANGES):
        return True
    return False


def _is_ascii_letter(ch: str) -> bool:
    """Return True if the character is an ASCII letter (a-z, A-Z)."""
    return bool(re.match(r"[A-Za-z]", ch))


def detect_language(text: str) -> tuple[str, float]:
    """
    Detect whether the provided text is primarily Chinese or English.

    Counts CJK characters and ASCII letters.  Returns the detected language
    and a confidence ratio in [0, 1].

    Args:
        text: The extracted text to analyze.

    Returns:
        A (language, confidence) tuple:
            language  — "zh" (Chinese), "en" (English), or "unknown"
            confidence — float in [0, 1]; higher is more confident
    """
    if not text or len(text.strip()) < 10:
        return ("unknown", 0.0)

    cjk_count = 0
    ascii_count = 0

    for ch in text:
        if _is_cjk_char(ch):
            cjk_count += 1
        elif _is_ascii_letter(ch):
            ascii_count += 1

    meaningful = cjk_count + ascii_count
    if meaningful == 0:
        return ("unknown", 0.0)

    cjk_ratio = cjk_count / meaningful

    if cjk_ratio > 0.30:
        return ("zh", round(cjk_ratio, 3))
    else:
        return ("en", round(1.0 - cjk_ratio, 3))


def assess_text_quality(full_text: str, page_count: int, min_chars_per_page: int = 80) -> dict:
    """
    Assess whether the PDF contains extractable text or is likely a scan.

    Args:
        full_text: Complete extracted text from all pages.
        page_count: Total page count of the PDF.
        min_chars_per_page: Threshold below which a page is considered sparse.

    Returns:
        Dict with keys:
            scanned_likely — bool, True if the PDF appears to be scanned
            chars_per_page — float, average characters per page
            warning        — str or None, human-readable warning message
    """
    total_chars = len(full_text.strip())
    chars_per_page = total_chars / max(page_count, 1)

    scanned_likely = chars_per_page < min_chars_per_page

    if scanned_likely:
        warning = (
            "⚠️ This PDF may be a scanned document. "
            f"Only {chars_per_page:.0f} characters of text were extracted per page on average. "
            "OCR support will be added in a future release."
        )
    else:
        warning = None

    return {
        "scanned_likely": scanned_likely,
        "chars_per_page": round(chars_per_page, 1),
        "warning": warning,
    }


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PdfPage:
    """A single page extracted from a PDF document.

    Attributes:
        page_number: 1-indexed, human-readable page number.
        text: The full extracted text of this page.
        char_count: Number of characters in the extracted text.
    """

    page_number: int
    text: str
    char_count: int


@dataclass
class PdfDocument:
    """Structured representation of a parsed PDF document."""

    file_name: str
    page_count: int = 0
    metadata: dict = field(default_factory=dict)
    full_text: str = ""
    text_preview: str = ""
    file_size_kb: float = 0.0

    # Language detection
    language: str = "unknown"        # "zh", "en", or "unknown"
    language_confidence: float = 0.0  # 0.0 – 1.0

    # Scan assessment
    scanned_likely: bool = False
    scanned_warning: Optional[str] = None
    chars_per_page: float = 0.0

    # Page-level access
    pages: list[PdfPage] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main parsing function
# ---------------------------------------------------------------------------


def parse_pdf(
    file_bytes: bytes,
    file_name: str,
    preview_chars: int = 5000,
) -> PdfDocument:
    """
    Parse a PDF from raw bytes and return a PdfDocument.

    Extracts text (preserving Chinese Unicode), detects document language,
    and warns if the PDF appears to be a scanned image without text.

    Args:
        file_bytes: Raw PDF file bytes.
        file_name: Original filename (for display).
        preview_chars: Number of characters for the text preview.

    Returns:
        PdfDocument with extracted metadata, text, language, and quality info.
    """
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")

    # --- Extract text from every page --------------------------------------
    full_text_parts: list[str] = []
    pages: list[PdfPage] = []
    for page_num, page in enumerate(doc, start=1):
        page_text = page.get_text()
        full_text_parts.append(page_text)
        pages.append(PdfPage(
            page_number=page_num,
            text=page_text,
            char_count=len(page_text),
        ))

    full_text = "\n".join(full_text_parts)
    text_preview = full_text[:preview_chars]

    file_size_kb = len(file_bytes) / 1024.0

    # --- Language detection ------------------------------------------------
    language, language_confidence = detect_language(full_text)

    # --- Scan assessment ---------------------------------------------------
    quality = assess_text_quality(full_text, doc.page_count)

    pdf_document = PdfDocument(
        file_name=file_name,
        page_count=doc.page_count,
        metadata=dict(doc.metadata),
        full_text=full_text,
        text_preview=text_preview,
        file_size_kb=round(file_size_kb, 1),
        language=language,
        language_confidence=language_confidence,
        scanned_likely=quality["scanned_likely"],
        scanned_warning=quality["warning"],
        chars_per_page=quality["chars_per_page"],
        pages=pages,
    )

    doc.close()
    return pdf_document
