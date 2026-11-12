import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPreparedInquiry,
  checkContactAntiSpam,
  FIELD_MAX_LENGTHS,
  MAX_MAILTO_URI_LENGTH,
  sanitizeSingleLine,
  validateContactForm,
  type ContactFormValues,
} from "./contact-validation";

const baseValid: ContactFormValues = {
  fullName: "Rajesh Sharma",
  businessEmail: "rajesh@sharmatraders.in",
  phone: "+91 9876543210",
  businessName: "Sharma Industrial Traders",
  subject: "Pricing inquiry",
  message: "We would like details on SriLekh accounting plans for 2 companies.",
  honeypot: "",
};

test("Contact form validation & mailto handoff", async (t) => {
  await t.test("rejects missing required fields and short messages", () => {
    const errors = validateContactForm({
      fullName: "   ",
      businessEmail: "",
      phone: "123",
      businessName: "",
      subject: "",
      message: "short",
      honeypot: "",
    });
    assert.ok(errors.fullName);
    assert.ok(errors.businessEmail);
    assert.ok(errors.phone);
    assert.ok(errors.subject);
    assert.ok(errors.message);
  });

  await t.test("rejects malformed email addresses", () => {
    const errors = validateContactForm({
      ...baseValid,
      businessEmail: "not-an-email",
    });
    assert.equal(Object.keys(errors).length, 1);
    assert.ok(errors.businessEmail);
  });

  await t.test("rejects oversized fields exceeding max lengths", () => {
    const errors = validateContactForm({
      ...baseValid,
      subject: "A".repeat(FIELD_MAX_LENGTHS.subject + 1),
      message: "B".repeat(FIELD_MAX_LENGTHS.message + 1),
    });
    assert.ok(errors.subject);
    assert.ok(errors.message);
  });

  await t.test("accepts valid form without optional fields", () => {
    const errors = validateContactForm({
      ...baseValid,
      phone: "",
      businessName: "",
    });
    assert.equal(Object.keys(errors).length, 0);
  });

  await t.test("anti-spam rejects filled honeypot or instant bot submit", () => {
    assert.ok(checkContactAntiSpam("https://spam.example", 1000, 5000));
    assert.ok(checkContactAntiSpam("", 1000, 1500));
    assert.equal(checkContactAntiSpam("", 1000, 3000), null);
  });

  await t.test("sanitizes control characters and enforces safe mailto URI length", () => {
    assert.equal(sanitizeSingleLine("Test\r\nBcc: evil@attacker.com\x00"), "Test Bcc: evil@attacker.com");

    const prepared = buildPreparedInquiry(baseValid);
    assert.ok(prepared.mailtoHref.startsWith("mailto:support@srilekh.com?"));
    assert.ok(prepared.mailtoHref.includes(encodeURIComponent("[SriLekh Contact] Pricing inquiry")));
    assert.equal(prepared.isMailtoTruncated, false);

    const longPrepared = buildPreparedInquiry({
      ...baseValid,
      message: "This is a realistic detailed business accounting inquiry. ".repeat(26),
    });
    assert.ok(longPrepared.mailtoHref.length <= MAX_MAILTO_URI_LENGTH);
    assert.equal(longPrepared.isMailtoTruncated, true);
    assert.ok(longPrepared.fullText.includes("This is a realistic detailed business accounting inquiry."));
  });
});
