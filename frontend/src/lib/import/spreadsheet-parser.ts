import { readSheet } from "read-excel-file/browser";

export const MAX_SPREADSHEET_SIZE_BYTES = 15 * 1024 * 1024;
export const MAX_SPREADSHEET_UNCOMPRESSED_BYTES = 50 * 1024 * 1024;
export const MAX_SPREADSHEET_ZIP_ENTRIES = 250;
export const MAX_SPREADSHEET_ZIP_RATIO = 100;
export const MAX_SPREADSHEET_ROWS = 50000;

const ALLOWED_SPREADSHEET_MIME_TYPES = new Set([
  "text/csv",
  "text/plain",
  "application/csv",
  "text/x-csv",
  "application/x-csv",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/octet-stream",
  "application/zip",
]);

export function sanitizeSpreadsheetExportCell(value: unknown): string {
  const str = String(value ?? "");
  // Guard against spreadsheet formula injection when CSV/XLSX data is re-exported
  if (/^[=+\-@\t\r]/.test(str)) {
    return `'${str}`;
  }
  return str;
}

export interface ParsedSpreadsheetNumber {
  valid: boolean;
  isEmpty: boolean;
  value: number;
  error?: string;
}

/**
 * Parses a non-negative spreadsheet monetary or quantity cell without silently
 * flipping negative values (e.g. -500 -> 500) or ignoring malformed decimals.
 */
export function parseNonNegativeSpreadsheetNumber(
  raw: unknown,
  options: { defaultValue?: number; integerOnly?: boolean } = {}
): ParsedSpreadsheetNumber {
  const defaultValue = options.defaultValue ?? 0;
  if (raw === null || raw === undefined) {
    return { valid: true, isEmpty: true, value: defaultValue };
  }
  if (typeof raw === "number") {
    if (!Number.isFinite(raw) || raw < 0) {
      return { valid: false, isEmpty: false, value: defaultValue, error: "Negative or non-finite numeric value." };
    }
    return {
      valid: true,
      isEmpty: false,
      value: options.integerOnly ? Math.trunc(raw) : raw,
    };
  }

  const trimmed = String(raw).trim();
  if (!trimmed) {
    return { valid: true, isEmpty: true, value: defaultValue };
  }

  // Strip safe currency prefixes and thousand separators while preserving signs/format errors
  const cleaned = trimmed
    .replace(/^[₹$]\s*/u, "")
    .replace(/^(?:rs\.?|inr)\s*/i, "")
    .replace(/,/g, "")
    .trim();

  if (/^-\s*\d/.test(cleaned) || /^\(.*\)$/.test(cleaned)) {
    return { valid: false, isEmpty: false, value: defaultValue, error: "Negative values are not allowed." };
  }

  const pattern = options.integerOnly ? /^\d+$/ : /^\d+(?:\.\d+)?$/;
  if (!pattern.test(cleaned)) {
    return { valid: false, isEmpty: false, value: defaultValue, error: "Malformed numeric value." };
  }

  const parsed = options.integerOnly ? parseInt(cleaned, 10) : parseFloat(cleaned);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return { valid: false, isEmpty: false, value: defaultValue, error: "Invalid numeric value." };
  }

  return { valid: true, isEmpty: false, value: parsed };
}

export function validateSpreadsheetFilename(filename: string): string {
  if (!filename || typeof filename !== "string") {
    throw new Error("Missing spreadsheet filename.");
  }
  if (filename.length > 255) {
    throw new Error("Spreadsheet filename exceeds 255 character limit.");
  }
  if (
    filename.includes("\0") ||
    filename.includes("/") ||
    filename.includes("\\") ||
    filename.includes("..") ||
    /[\x00-\x1f\x7f]/.test(filename)
  ) {
    throw new Error("Unsafe spreadsheet filename rejected.");
  }
  return filename.toLowerCase();
}

function validateSpreadsheetMetadata(file: File): string {
  const lowerName = validateSpreadsheetFilename(file.name);
  if (typeof file.size !== "number" || file.size <= 0) {
    throw new Error("Spreadsheet file is empty (0 bytes).");
  }
  if (file.size > MAX_SPREADSHEET_SIZE_BYTES) {
    throw new Error("Spreadsheet exceeds the 15 MB size limit.");
  }
  const mime = (file.type || "").split(";")[0].trim().toLowerCase();
  if (mime && !ALLOWED_SPREADSHEET_MIME_TYPES.has(mime)) {
    throw new Error(`Disallowed spreadsheet MIME type: ${mime}.`);
  }
  if (
    lowerName.endsWith(".csv") &&
    mime === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  ) {
    throw new Error("Disallowed spreadsheet MIME type mismatch for .csv file.");
  }
  return lowerName;
}

/**
 * Inspects a ZIP/OOXML byte buffer's End of Central Directory & Central Directory
 * headers before passing it to read-excel-file to block ZIP bombs, huge uncompressed
 * entries, excessive member counts, and ZIP entry path traversal.
 */
export function validateXlsxArchiveBytes(bytes: Uint8Array): void {
  // Standard ZIP Local File Header magic: PK\x03\x04
  if (bytes.length < 4 || bytes[0] !== 0x50 || bytes[1] !== 0x4b || bytes[2] !== 0x03 || bytes[3] !== 0x04) {
    throw new Error("Invalid .xlsx file signature. Expected OOXML ZIP archive.");
  }
  if (bytes.length < 22) {
    throw new Error("Corrupted .xlsx file: archive is truncated.");
  }

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const searchStart = Math.max(0, bytes.length - 65557);
  let eocdOffset = -1;
  for (let i = bytes.length - 22; i >= searchStart; i -= 1) {
    if (view.getUint32(i, true) === 0x06054b50) {
      eocdOffset = i;
      break;
    }
  }
  if (eocdOffset === -1) {
    throw new Error("Corrupted .xlsx file: missing ZIP End-of-Central-Directory record.");
  }

  const totalEntries = view.getUint16(eocdOffset + 10, true);
  const cdSize = view.getUint32(eocdOffset + 12, true);
  const cdOffset = view.getUint32(eocdOffset + 16, true);

  if (totalEntries === 0 || totalEntries > MAX_SPREADSHEET_ZIP_ENTRIES) {
    throw new Error(
      `Spreadsheet archive entry count (${totalEntries}) exceeds safety bounds.`
    );
  }
  if (cdOffset >= bytes.length || cdOffset + cdSize > bytes.length) {
    throw new Error("Corrupted .xlsx file: invalid Central Directory bounds.");
  }

  const decoder = new TextDecoder("utf-8", { fatal: false });
  let pos = cdOffset;
  let totalUncompressed = 0;

  for (let entry = 0; entry < totalEntries; entry += 1) {
    if (pos + 46 > bytes.length || view.getUint32(pos, true) !== 0x02014b50) {
      throw new Error("Corrupted .xlsx file: malformed ZIP Central Directory header.");
    }
    const compressedSize = view.getUint32(pos + 20, true);
    const uncompressedSize = view.getUint32(pos + 24, true);
    const nameLen = view.getUint16(pos + 28, true);
    const extraLen = view.getUint16(pos + 30, true);
    const commentLen = view.getUint16(pos + 32, true);

    if (compressedSize === 0xffffffff || uncompressedSize === 0xffffffff) {
      throw new Error("Spreadsheet ZIP64 archives exceed decompression safety limits.");
    }
    if (pos + 46 + nameLen > bytes.length) {
      throw new Error("Corrupted .xlsx file: truncated ZIP entry metadata.");
    }

    const entryName = decoder.decode(bytes.subarray(pos + 46, pos + 46 + nameLen));
    if (
      entryName.includes("\0") ||
      entryName.includes("..") ||
      entryName.startsWith("/") ||
      entryName.startsWith("\\")
    ) {
      throw new Error("Unsafe path inside .xlsx archive rejected.");
    }

    if (uncompressedSize > MAX_SPREADSHEET_UNCOMPRESSED_BYTES) {
      throw new Error("Spreadsheet archive entry exceeds 50 MB decompressed safety limit.");
    }
    totalUncompressed += uncompressedSize;
    if (totalUncompressed > MAX_SPREADSHEET_UNCOMPRESSED_BYTES) {
      throw new Error("Spreadsheet archive exceeds 50 MB total decompressed limit.");
    }

    pos += 46 + nameLen + extraLen + commentLen;
  }

  if (
    totalUncompressed > 1024 * 1024 &&
    bytes.length > 0 &&
    totalUncompressed / bytes.length > MAX_SPREADSHEET_ZIP_RATIO
  ) {
    throw new Error("Spreadsheet archive exceeds safe compression ratio (suspected ZIP bomb).");
  }
}

function assertTextNotBinary(text: string): void {
  if (
    text.includes("\0") ||
    text.startsWith("%PDF-") ||
    text.startsWith("PK\x03\x04") ||
    text.startsWith("MZ")
  ) {
    throw new Error("Invalid CSV file: binary or executable content detected.");
  }
}

export function parseCsvToRows(csvText: string): string[][] {
  assertTextNotBinary(csvText);
  const normalized = csvText.replace(/^\uFEFF/, "");
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < normalized.length; i += 1) {
    const ch = normalized[i];
    const next = normalized[i + 1];

    if (inQuotes) {
      if (ch === '"' && next === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        cell += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\r" && next === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
      i += 1;
    } else if (ch === "\n" || ch === "\r") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += ch;
    }

    if (rows.length > MAX_SPREADSHEET_ROWS) {
      throw new Error(`Spreadsheet exceeds maximum allowed ${MAX_SPREADSHEET_ROWS} rows.`);
    }
  }

  if (inQuotes) {
    throw new Error("Malformed CSV: unclosed quoted field.");
  }

  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  if (rows.length > MAX_SPREADSHEET_ROWS) {
    throw new Error(`Spreadsheet exceeds maximum allowed ${MAX_SPREADSHEET_ROWS} rows.`);
  }
  return rows;
}

export async function parseSpreadsheetFileToRows(file: File): Promise<unknown[][]> {
  const lowerName = validateSpreadsheetMetadata(file);

  if (lowerName.endsWith(".csv")) {
    const buf = new Uint8Array(await file.arrayBuffer());
    if (buf.length === 0) {
      throw new Error("Spreadsheet file is empty (0 bytes).");
    }
    if (buf.length > MAX_SPREADSHEET_SIZE_BYTES) {
      throw new Error("Spreadsheet exceeds the 15 MB size limit.");
    }
    if (buf.includes(0)) {
      throw new Error("Invalid CSV file: binary null bytes detected.");
    }
    const text = new TextDecoder("utf-8", { fatal: false }).decode(buf);
    return parseCsvToRows(text);
  }

  if (lowerName.endsWith(".xlsx")) {
    const buf = new Uint8Array(await file.arrayBuffer());
    if (buf.length > MAX_SPREADSHEET_SIZE_BYTES) {
      throw new Error("Spreadsheet exceeds the 15 MB size limit.");
    }
    validateXlsxArchiveBytes(buf);
    const rows = await readSheet(file, 1);
    if (rows.length > MAX_SPREADSHEET_ROWS) {
      throw new Error(`Spreadsheet exceeds maximum allowed ${MAX_SPREADSHEET_ROWS} rows.`);
    }
    return rows;
  }

  if (lowerName.endsWith(".xls")) {
    throw new Error(
      "Legacy binary .xls files are disabled in browser parsing for security. Please save as .xlsx or .csv and upload again."
    );
  }

  throw new Error("Unsupported spreadsheet format. Upload .xlsx or .csv.");
}
