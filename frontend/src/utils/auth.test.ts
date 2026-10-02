import { test, describe } from 'node:test';
import assert from 'node:assert';
import { canPerformAccounting, isReadOnlyUser, hasRole } from './auth.ts';

describe('Auth & Permission Utilities', () => {
  test('canPerformAccounting returns false when no user is logged in', () => {
    assert.strictEqual(canPerformAccounting(), false);
  });

  test('isReadOnlyUser returns true when no user is logged in', () => {
    assert.strictEqual(isReadOnlyUser(), true);
  });

  test('hasRole returns false when no user is logged in', () => {
    assert.strictEqual(hasRole(['ADMIN', 'OWNER']), false);
  });
});
