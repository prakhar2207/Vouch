import { readSheet } from "read-excel-file/browser";

export const MAX_SPREADSHEET_SIZE_BYTES = 15 * 1024 * 1024;
export const MAX_SPREADSHEET_ROWS = 50000;

export function sanitizeSpreadsheetExportCell(value: unknown): string {
  const str = String(value ?? "");
  // Guard against spreadsheet formula injection when CSV/XLSX data is re-exported
  if (/^[=+\-@\t\r]/.test(str)) {
    return `'${str}`;
  }
  return str;
}

export function parseCsvToRows(csvText: string): string[][] {
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
  if (file.size > MAX_SPREADSHEET_SIZE_BYTES) {
    throw new Error("Spreadsheet exceeds the 15 MB size limit.");
  }

  const lowerName = file.name.toLowerCase();
  if (lowerName.endsWith(".csv")) {
    const text = await file.text();
    return parseCsvToRows(text);
  }
  if (lowerName.endsWith(".xlsx")) {
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
