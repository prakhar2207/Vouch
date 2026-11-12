import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { unzipSync, zipSync, strToU8 } from "fflate";
import {
  MAX_SPREADSHEET_ROWS,
  MAX_SPREADSHEET_SIZE_BYTES,
  parseCsvToRows,
  parseNonNegativeSpreadsheetNumber,
  parseSpreadsheetFileToRows,
  sanitizeSpreadsheetExportCell,
} from "./spreadsheet-parser";

function createMinimalXlsxFile(name = "pricelist.xlsx", type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): File {
  // Minimal valid OOXML workbook with sharedStrings.xml so read-excel-file parses it cleanly
  const contentTypes =
    '<?xml version="1.0" encoding="UTF-8"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-officedocument.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
    '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>' +
    "</Types>";
  const rels =
    '<?xml version="1.0" encoding="UTF-8"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
    "</Relationships>";
  const wbRels =
    '<?xml version="1.0" encoding="UTF-8"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>' +
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>' +
    "</Relationships>";
  const sharedStrings =
    '<?xml version="1.0" encoding="UTF-8"?>' +
    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="3" uniqueCount="3">' +
    "<si><t>Item Name</t></si><si><t>Rate</t></si><si><t>V-Belt A42</t></si>" +
    "</sst>";
  const workbook =
    '<?xml version="1.0" encoding="UTF-8"?>' +
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
    '<sheets><sheet name="PriceList" sheetId="1" r:id="rId1"/></sheets>' +
    "</workbook>";
  const sheet1 =
    '<?xml version="1.0" encoding="UTF-8"?>' +
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
    '<dimension ref="A1:B2"/>' +
    "<sheetData>" +
    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>' +
    '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>425</v></c></row>' +
    "</sheetData>" +
    "</worksheet>";

  const zipped = zipSync({
    "[Content_Types].xml": strToU8(contentTypes),
    "_rels/.rels": strToU8(rels),
    "xl/_rels/workbook.xml.rels": strToU8(wbRels),
    "xl/sharedStrings.xml": strToU8(sharedStrings),
    "xl/workbook.xml": strToU8(workbook),
    "xl/worksheets/sheet1.xml": strToU8(sheet1),
  });
  assert.ok(Object.keys(unzipSync(zipped)).includes("xl/worksheets/sheet1.xml"));
  const ab = zipped.buffer.slice(zipped.byteOffset, zipped.byteOffset + zipped.byteLength);
  return new File([ab], name, { type });
}

describe("Spreadsheet Parser (safe xlsx replacement & CSV hardening)", () => {
  it("parses RFC-4180 CSV with BOM, quoted commas, escaped quotes, and multiline cells", () => {
    const csv = '\uFEFFItem,Description,MRP\r\n"A42 ""Heavy"" Belt","Includes, ""special"" ply\nline 2",425\r\nB50,Standard,510';
    const rows = parseCsvToRows(csv);
    assert.equal(rows.length, 3);
    assert.deepEqual(rows[0], ["Item", "Description", "MRP"]);
    assert.deepEqual(rows[1], ['A42 "Heavy" Belt', 'Includes, "special" ply\nline 2', "425"]);
    assert.deepEqual(rows[2], ["B50", "Standard", "510"]);
  });

  it("rejects malformed CSV with unclosed quotes or embedded binary null bytes", () => {
    assert.throws(() => parseCsvToRows('Item,MRP\n"Unclosed quote,450'), /unclosed quoted field/i);
    assert.throws(() => parseCsvToRows("Item\x00,MRP\nBelt,450"), /binary or executable/i);
  });

  it("parses valid .xlsx files via read-excel-file without SheetJS/xlsx", async () => {
    const file = createMinimalXlsxFile();
    const rows = await parseSpreadsheetFileToRows(file);
    assert.equal(rows.length, 2);
    assert.deepEqual(rows[0], ["Item Name", "Rate"]);
    assert.equal(rows[1][0], "V-Belt A42");
    assert.equal(rows[1][1], 425);
  });

  it("rejects legacy binary .xls, zero-byte empty files, and unsupported extensions", async () => {
    const emptyCsv = new File([], "empty.csv", { type: "text/csv" });
    await assert.rejects(() => parseSpreadsheetFileToRows(emptyCsv), /empty \(0 bytes\)/i);

    const legacy = new File([new Uint8Array([0xd0, 0xcf, 0x11, 0xe0])], "legacy.xls");
    await assert.rejects(() => parseSpreadsheetFileToRows(legacy), /save as \.xlsx or \.csv/i);

    const badExt = new File(["plain"], "malware.exe");
    await assert.rejects(() => parseSpreadsheetFileToRows(badExt), /Unsupported spreadsheet format/i);
  });

  it("rejects malicious filenames (path traversal, slashes, null bytes) and unexpected MIME types", async () => {
    const traversal = new File(["Item,Rate\nA,10"], "../../evil.csv", { type: "text/csv" });
    await assert.rejects(() => parseSpreadsheetFileToRows(traversal), /Unsafe spreadsheet filename/i);

    const nullByte = new File(["Item,Rate\nA,10"], "evil\0.csv", { type: "text/csv" });
    await assert.rejects(() => parseSpreadsheetFileToRows(nullByte), /Unsafe spreadsheet filename/i);

    const htmlMime = new File(["<html><script>alert(1)</script></html>"], "report.csv", { type: "text/html" });
    await assert.rejects(() => parseSpreadsheetFileToRows(htmlMime), /Disallowed spreadsheet MIME/i);

    const exeSpoof = new File(["MZ\x90\x00bad"], "fake.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    await assert.rejects(() => parseSpreadsheetFileToRows(exeSpoof), /Invalid \.xlsx file signature/i);

    const pdfAsCsv = new File(["%PDF-1.7\n1 0 obj"], "fake.csv", { type: "text/csv" });
    await assert.rejects(() => parseSpreadsheetFileToRows(pdfAsCsv), /binary or executable/i);
  });

  it("blocks .xlsx ZIP bombs exceeding decompressed limits/ratios and path traversal entries before parsing", async () => {
    // 1. Over-ratio / >1MB highly compressed zero-filled XML bomb (~55 MB zeros -> small zip)
    const bombBuf = zipSync({
      "xl/worksheets/sheet1.xml": new Uint8Array(52 * 1024 * 1024),
    });
    const bombAb = bombBuf.buffer.slice(bombBuf.byteOffset, bombBuf.byteOffset + bombBuf.byteLength);
    const bombFile = new File([bombAb], "bomb.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    await assert.rejects(() => parseSpreadsheetFileToRows(bombFile), /50 MB|compression ratio|ZIP bomb/i);

    // 2. ZIP member path traversal
    const zipSlip = zipSync({
      "../../evil.xml": strToU8("<x/>"),
    });
    const slipAb = zipSlip.buffer.slice(zipSlip.byteOffset, zipSlip.byteOffset + zipSlip.byteLength);
    const slipFile = new File([slipAb], "slip.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    await assert.rejects(() => parseSpreadsheetFileToRows(slipFile), /Unsafe path inside \.xlsx/i);

    // 3. Corrupted truncated xlsx
    const corrupt = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00, 0x00])], "corrupt.xlsx");
    await assert.rejects(() => parseSpreadsheetFileToRows(corrupt), /Corrupted \.xlsx/i);
  });

  it("enforces 15 MB size limit and 50,000 row ceiling against DoS payloads", async () => {
    const hugeFakeFile = {
      name: "huge.csv",
      type: "text/csv",
      size: MAX_SPREADSHEET_SIZE_BYTES + 1,
    } as File;
    await assert.rejects(() => parseSpreadsheetFileToRows(hugeFakeFile), /15 MB size limit/i);

    const tooManyRows = Array.from({ length: MAX_SPREADSHEET_ROWS + 1 }, (_, i) => `R${i},1`).join("\n");
    assert.throws(() => parseCsvToRows(tooManyRows), /exceeds maximum allowed/i);
  });

  it("rejects negative prices and malformed numbers cleanly instead of flipping signs positive", () => {
    assert.deepEqual(parseNonNegativeSpreadsheetNumber("₹1,450.50"), { valid: true, isEmpty: false, value: 1450.5 });
    assert.deepEqual(parseNonNegativeSpreadsheetNumber("Rs. 250"), { valid: true, isEmpty: false, value: 250 });
    assert.deepEqual(parseNonNegativeSpreadsheetNumber(""), { valid: true, isEmpty: true, value: 0 });
    assert.equal(parseNonNegativeSpreadsheetNumber("-500").valid, false);
    assert.equal(parseNonNegativeSpreadsheetNumber("(500)").valid, false);
    assert.equal(parseNonNegativeSpreadsheetNumber("12.34.56").valid, false);
    assert.equal(parseNonNegativeSpreadsheetNumber("NaN").valid, false);
    assert.equal(parseNonNegativeSpreadsheetNumber(-10).valid, false);
  });

  it("neutralizes spreadsheet formula injection prefixes on export", () => {
    assert.equal(sanitizeSpreadsheetExportCell("=CMD('calc')"), "'=CMD('calc')");
    assert.equal(sanitizeSpreadsheetExportCell("+1+2"), "'+1+2");
    assert.equal(sanitizeSpreadsheetExportCell("-A1"), "'-A1");
    assert.equal(sanitizeSpreadsheetExportCell("@SUM(1,2)"), "'@SUM(1,2)");
    assert.equal(sanitizeSpreadsheetExportCell("Apex Belting Store"), "Apex Belting Store");
  });
});
