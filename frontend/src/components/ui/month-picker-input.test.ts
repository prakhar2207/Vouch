import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parsePeriodToDisplay, parseUserInputToPeriod } from "./MonthPickerInput";

describe("MonthPickerInput Period Parsing & Formatting", () => {
  it("formats normalized MMYYYY to human-readable MMMM YYYY", () => {
    assert.equal(parsePeriodToDisplay("042026"), "April 2026");
    assert.equal(parsePeriodToDisplay("102026"), "October 2026");
    assert.equal(parsePeriodToDisplay("012025"), "January 2025");
    assert.equal(parsePeriodToDisplay("122027"), "December 2027");
  });

  it("parses direct keyboard input: Full month name + year", () => {
    const res = parseUserInputToPeriod("April 2026");
    assert.ok(res);
    assert.equal(res?.normalized, "042026");
    assert.equal(res?.display, "April 2026");

    const res2 = parseUserInputToPeriod("October 2026");
    assert.ok(res2);
    assert.equal(res2?.normalized, "102026");
    assert.equal(res2?.display, "October 2026");
  });

  it("parses direct keyboard input: Short month name + year", () => {
    const res = parseUserInputToPeriod("Apr 2026");
    assert.ok(res);
    assert.equal(res?.normalized, "042026");
    assert.equal(res?.display, "April 2026");

    const res2 = parseUserInputToPeriod("Oct 2026");
    assert.ok(res2);
    assert.equal(res2?.normalized, "102026");
    assert.equal(res2?.display, "October 2026");
  });

  it("parses direct keyboard input: Numeric MMYYYY (e.g. 042026)", () => {
    const res = parseUserInputToPeriod("042026");
    assert.ok(res);
    assert.equal(res?.normalized, "042026");
    assert.equal(res?.display, "April 2026");
  });

  it("parses direct keyboard input: Slashed or hyphenated (MM/YYYY or YYYY-MM)", () => {
    const res1 = parseUserInputToPeriod("04/2026");
    assert.ok(res1);
    assert.equal(res1?.normalized, "042026");

    const res2 = parseUserInputToPeriod("2026-10");
    assert.ok(res2);
    assert.equal(res2?.normalized, "102026");
    assert.equal(res2?.display, "October 2026");
  });

  it("rejects invalid non-period inputs", () => {
    assert.equal(parseUserInputToPeriod(""), null);
    assert.equal(parseUserInputToPeriod("invalid text"), null);
    assert.equal(parseUserInputToPeriod("132026"), null); // month 13
    assert.equal(parseUserInputToPeriod("002026"), null); // month 0
    assert.equal(parseUserInputToPeriod("April 2010"), null); // year before 2017
  });
});
