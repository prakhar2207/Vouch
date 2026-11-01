# Testing Isolation & Sandbox Invariant

## Critical Rule: Zero Test Data in User Accounts

### Invariant:
- **Never insert, modify, or post test data into user accounts.**
- **`Maa Annapurna Belting Store` (`5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`) is a protected user production account.** No test vouchers, test bank statements, or mock entries may ever be introduced into it.
- **Dedicated Sandbox**: Use strictly **`Apex Belting & Industrial Store (Demo)` (`4e62863a-08f9-4e99-b0bd-64873acfdd33`)** for all testing, integration verification, concurrency stress-tests, and demonstration data.

### Enforcement:
- Any script or test suite running against the database must explicitly check:
  ```python
  TEST_COMPANY_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33' # Apex Belting & Industrial Store (Demo)
  if str(company.id) != TEST_COMPANY_ID:
      raise PermissionError(f"Test data creation prohibited on company {company.id} ({company.name}). Use Apex Belting Store only.")
  ```
- This rule is of the highest importance and cannot be overridden without explicit instructions from the user.
