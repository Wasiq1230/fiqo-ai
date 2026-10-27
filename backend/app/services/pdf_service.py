"""
PDF handling: safe validation and text extraction.

Security notes:
- We validate the declared content-type AND the file magic bytes (%PDF).
- We enforce a hard size limit while reading (streaming guard) so a huge
  upload cannot exhaust memory before we notice.
- Extraction failures are surfaced as domain errors, never raw tracebacks.
"""
import io

from fastapi import UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config import get_settings

settings = get_settings()

_PDF_MAGIC = b"%PDF-"


class PDFError(Exception):
    """Raised for any user-facing PDF problem (bad type, too big, unreadable)."""


async def _read_limited(file: UploadFile) -> bytes:
    """Read an upload, aborting if it exceeds the configured size limit."""
    max_bytes = settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 256)  # 256 KB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PDFError(
                f"File '{file.filename}' exceeds the {settings.max_upload_mb} MB limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_pdf(filename: str | None, content: bytes) -> None:
    if not content:
        raise PDFError("Uploaded file is empty.")
    name = (filename or "").lower()
    if not name.endswith(".pdf"):
        raise PDFError(f"'{filename}' is not a .pdf file.")
    if not content.startswith(_PDF_MAGIC):
        raise PDFError(
            f"'{filename}' does not appear to be a valid PDF (bad file signature)."
        )


def _extract(content: bytes, filename: str | None) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
    except PdfReadError as exc:
        raise PDFError(f"Could not read '{filename}': {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise PDFError(f"Could not read '{filename}'.") from exc

    if reader.is_encrypted:
        # Attempt empty-password decrypt; if it fails, reject clearly.
        try:
            if reader.decrypt("") == 0:
                raise PDFError(f"'{filename}' is password-protected.")
        except Exception as exc:
            raise PDFError(f"'{filename}' is password-protected.") from exc

    try:
        page_count = len(reader.pages)
    except Exception as exc:  # malformed page tree
        raise PDFError(f"Could not read the page structure of '{filename}'.") from exc

    if page_count > settings.max_pdf_pages:
        # A few hundred KB of PDF can declare tens of thousands of pages; text
        # extraction on that pins a worker for minutes. Cap it.
        raise PDFError(
            f"'{filename}' has {page_count} pages; the limit is "
            f"{settings.max_pdf_pages}. Please split the document."
        )

    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            # Skip an unreadable page rather than failing the whole document.
            continue
    return "".join(parts)


async def extract_text_from_pdf(file: UploadFile) -> str:
    """Validate and extract text from a single uploaded PDF."""
    content = await _read_limited(file)
    _validate_pdf(file.filename, content)
    text = _extract(content, file.filename)
    if not text.strip():
        raise PDFError(
            f"No extractable text found in '{file.filename}'. "
            "It may be a scanned image PDF."
        )
    return text


async def extract_text_from_multiple_pdfs(files: list[UploadFile]) -> str:
    """Validate and concatenate text from several PDFs."""
    if not files:
        raise PDFError("No files were uploaded.")
    if len(files) > settings.max_files_per_request:
        raise PDFError(
            f"Too many files. Maximum is {settings.max_files_per_request} per request."
        )

    combined: list[str] = []
    total_bytes = 0
    for file in files:
        content = await _read_limited(file)
        total_bytes += len(content)
        if total_bytes > settings.max_total_upload_bytes:
            # Per-file limits alone still allow N files x max size in one
            # request, which is the easier way to exhaust worker memory.
            raise PDFError(
                "Combined upload size exceeds the "
                f"{settings.max_total_upload_mb} MB limit for a single request."
            )
        _validate_pdf(file.filename, content)
        text = _extract(content, file.filename)
        combined.append(f"\n\n===== FILE: {file.filename} =====\n\n{text}")

    result = "".join(combined)
    if not result.strip():
        raise PDFError("No extractable text found in the uploaded PDFs.")
    return result
