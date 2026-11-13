import io
import os
import re
import zipfile
from typing import Iterable, Optional

MAX_IMPORT_FILE_SIZE = 15 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_XLSX_ZIP_ENTRIES = 250
MAX_XLSX_ZIP_RATIO = 100
MAX_IMPORT_ROWS = 50000

DISALLOWED_UPLOAD_MIME_PREFIXES = ("image/", "video/", "audio/")
DISALLOWED_UPLOAD_MIME_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "application/javascript",
    "text/javascript",
    "application/pdf",
    "application/x-msdownload",
    "application/x-executable",
    "application/x-dosexec",
    "application/x-sh",
    "application/x-shellscript",
}

_BINARY_SIGNATURES = (b"PK\x03\x04", b"%PDF-", b"MZ", b"\x7fELF", b"\xd0\xcf\x11\xe0")


class UploadValidationError(ValueError):
    """Raised when an uploaded spreadsheet, JSON, or XML file fails safety checks."""


def validate_upload_filename(filename: Optional[str], allowed_extensions: Iterable[str]) -> str:
    """Validates filename length, path traversal characters, control bytes, and extension."""
    if not filename or not isinstance(filename, str):
        raise UploadValidationError("Missing upload filename.")
    if len(filename) > 255:
        raise UploadValidationError("Filename exceeds the 255 character limit.")
    if (
        "\x00" in filename
        or "/" in filename
        or "\\" in filename
        or ".." in filename
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in filename)
    ):
        raise UploadValidationError("Unsafe filename rejected.")
    _, ext = os.path.splitext(filename.lower())
    allowed = {e.lower() for e in allowed_extensions}
    if ext not in allowed:
        allowed_str = ", ".join(sorted(allowed))
        raise UploadValidationError(
            f"Unsupported file format '{ext or 'unknown'}'. Allowed formats: {allowed_str}."
        )
    return ext


def validate_upload_metadata(
    uploaded_file,
    allowed_extensions: Iterable[str],
    max_bytes: int = MAX_IMPORT_FILE_SIZE,
) -> str:
    """Validates filename, declared size, and Content-Type before reading file bytes."""
    ext = validate_upload_filename(getattr(uploaded_file, "name", None), allowed_extensions)

    declared_size = getattr(uploaded_file, "size", None)
    if declared_size is not None:
        if declared_size <= 0:
            raise UploadValidationError("Uploaded file is empty (0 bytes).")
        if declared_size > max_bytes:
            raise UploadValidationError(f"Uploaded file exceeds the {max_bytes // (1024 * 1024)}MB maximum limit.")

    content_type = (getattr(uploaded_file, "content_type", "") or "").split(";")[0].strip().lower()
    if content_type:
        if content_type in DISALLOWED_UPLOAD_MIME_TYPES or any(
            content_type.startswith(prefix) for prefix in DISALLOWED_UPLOAD_MIME_PREFIXES
        ):
            raise UploadValidationError(f"Disallowed upload MIME type: {content_type}.")
    return ext


def read_validated_upload_bytes(
    uploaded_file,
    allowed_extensions: Iterable[str],
    max_bytes: int = MAX_IMPORT_FILE_SIZE,
) -> bytes:
    """Validates metadata and reads bounded bytes (handling missing/spoofed file.size)."""
    validate_upload_metadata(uploaded_file, allowed_extensions, max_bytes=max_bytes)
    if hasattr(uploaded_file, "seek"):
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
    raw = uploaded_file.read(max_bytes + 1)
    if not raw:
        raise UploadValidationError("Uploaded file is empty (0 bytes).")
    if len(raw) > max_bytes:
        raise UploadValidationError(f"Uploaded file exceeds the {max_bytes // (1024 * 1024)}MB maximum limit.")
    return raw


def validate_xlsx_zip_bytes(data: bytes) -> None:
    """Guards openpyxl against ZIP bombs, path traversal entries, and corrupt archives."""
    if len(data) < 4 or not data.startswith(b"PK\x03\x04"):
        raise UploadValidationError("Invalid .xlsx file signature. Expected OOXML ZIP archive.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data), "r")
    except zipfile.BadZipFile as exc:
        raise UploadValidationError("Corrupted .xlsx file: invalid ZIP structure.") from exc

    with zf:
        infos = zf.infolist()
        if not infos or len(infos) > MAX_XLSX_ZIP_ENTRIES:
            raise UploadValidationError(
                f"Spreadsheet archive entry count ({len(infos)}) exceeds safety bounds."
            )
        total_uncompressed = 0
        for info in infos:
            name = info.filename
            if "\x00" in name or ".." in name or name.startswith("/") or name.startswith("\\"):
                raise UploadValidationError("Unsafe path inside .xlsx archive rejected.")
            if info.file_size > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise UploadValidationError("Spreadsheet archive entry exceeds 50MB decompressed limit.")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise UploadValidationError("Spreadsheet archive exceeds 50MB total decompressed limit.")

        if (
            total_uncompressed > 1024 * 1024
            and len(data) > 0
            and (total_uncompressed / len(data)) > MAX_XLSX_ZIP_RATIO
        ):
            raise UploadValidationError("Spreadsheet archive exceeds safe compression ratio (suspected ZIP bomb).")


def validate_csv_bytes(data: bytes) -> None:
    """Rejects binary/executable payloads disguised as CSV files."""
    if not data:
        raise UploadValidationError("The CSV file is empty.")
    if b"\x00" in data or any(data.startswith(sig) for sig in _BINARY_SIGNATURES):
        raise UploadValidationError("Invalid CSV file: binary or executable content detected.")


def validate_xml_no_xxe(xml_text: str) -> None:
    """Blocks XML DOCTYPE and ENTITY declarations to prevent XXE / Billion Laughs DoS."""
    if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", xml_text[:32768], re.IGNORECASE):
        raise UploadValidationError("XML DOCTYPE/ENTITY declarations are rejected for security.")
