import { test, describe } from 'node:test';
import assert from 'node:assert';
import { ROLE_CAPABILITY_MAP } from './domain.ts';

describe('Domain Role Capabilities Matrix', () => {
  test('OWNER and ADMIN can create journals and manage settings', () => {
    assert.strictEqual(ROLE_CAPABILITY_MAP.OWNER.canCreateJournals, true);
    assert.strictEqual(ROLE_CAPABILITY_MAP.ADMIN.canCreateJournals, true);
    assert.strictEqual(ROLE_CAPABILITY_MAP.OWNER.canManageSettings, true);
    assert.strictEqual(ROLE_CAPABILITY_MAP.ADMIN.canManageSettings, true);
  });

  test('CA can create journals and contras but cannot manage company settings', () => {
    assert.strictEqual(ROLE_CAPABILITY_MAP.CA.canCreateJournals, true);
    assert.strictEqual(ROLE_CAPABILITY_MAP.CA.canCreateContras, true);
    assert.strictEqual(ROLE_CAPABILITY_MAP.CA.canManageSettings, false);
  });

  test('EMPLOYEE can create sales and purchases but not journals or contras', () => {
    assert.strictEqual(ROLE_CAPABILITY_MAP.EMPLOYEE.canCreateSales, true);
    assert.strictEqual(ROLE_CAPABILITY_MAP.EMPLOYEE.canCreatePurchases, true);
    assert.strictEqual(ROLE_CAPABILITY_MAP.EMPLOYEE.canCreateJournals, false);
    assert.strictEqual(ROLE_CAPABILITY_MAP.EMPLOYEE.canCreateContras, false);
    assert.strictEqual(ROLE_CAPABILITY_MAP.EMPLOYEE.isReadOnly, false);
  });

  test('VIEWER is read-only and cannot perform accounting mutations', () => {
    assert.strictEqual(ROLE_CAPABILITY_MAP.VIEWER.isReadOnly, true);
    assert.strictEqual(ROLE_CAPABILITY_MAP.VIEWER.canCreateSales, false);
    assert.strictEqual(ROLE_CAPABILITY_MAP.VIEWER.canCreateJournals, false);
  });
});
