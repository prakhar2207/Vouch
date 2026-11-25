# SriLekh GST ITC Shield — Round 2.4.7
## GSTR-2B Period Selector UX & Component Architecture Specification

**Component:** `MonthPickerInput.tsx` (`frontend/src/components/ui/MonthPickerInput.tsx`)  
**Target View:** `frontend/src/app/gst/itc-shield/page.tsx` (GSTR-2B Sync Modal)  
**Status:** Implemented, Tested & Certified  

---

### 1. Executive Summary & Problem Context

Prior to Round 2.4.7, the GSTR-2B sync modal used basic HTML `<select>` dropdowns hardcoded to a static list of months. This design had several limitations:
1. **Rigid period navigation**: Selecting months outside the preset dropdown required cumbersome clicking or was outright unsupported.
2. **Poor keyboard accessibility**: Power users, CAs, and accountants could not quickly type standard date abbreviations (e.g., `042026`, `Apr 26`, `2026-04`).
3. **Weak visual feedback**: Users lacked immediate clarity regarding whether a chosen range was valid or which months were covered.
4. **Day-level picker mismatch**: Standard browser HTML `<input type="date">` forces users to pick a specific day of the month, which contradicts GST statutory return periods that operate strictly at the monthly and quarterly statement level.

---

### 2. MonthPickerInput Architecture

The newly engineered `MonthPickerInput` is a specialized, accessible month-and-year picker designed specifically for statutory accounting workflows:

#### 2.1 Multi-Mode Input Support
Users can select a return period through two complementary interaction modes:
1. **Direct Keyboard Typing**:
   - Natural month name + year: `"April 2026"`, `"Apr 2026"`
   - Compact numeric representation: `"042026"`, `"04/2026"`, `"04-2026"`
   - ISO month format: `"2026-04"`
   The component parses keyboard input on blur or Enter key press, normalizes it into `MMYYYY`, and reformats the display string to standard `MMMM YYYY`.
2. **Visual Month/Year Grid Picker**:
   - Clicking the calendar button opens an interactive popover overlay.
   - Header with Year navigation (`<` previous year, `>` next year).
   - 3x4 grid displaying all 12 calendar months (`Jan` through `Dec`).
   - One-click month selection immediately closes the popover and commits the value.

#### 2.2 Statutory Range & Validation Rules
- **Normalized Format (`MMYYYY`)**: Internal state communicates with the backend strictly using the canonical 6-character statutory standard (e.g. `"042026"`).
- **Future Period Guard**: Periods beyond the current calendar month can be disabled (`maxPeriod`), preventing accidental requests for ungenerated future GSTR-2B returns.
- **Visual Error Feedback**: If an invalid or unparseable string is typed, the component highlights the input with a red border and resets to previous valid state or displays inline helper text.
- **Accessibility & Focus Management**:
  - Full keyboard navigation (Tab, Enter, Escape).
  - Pressing `Escape` or clicking outside automatically dismisses the popover.

---

### 3. Integration in GSTR-2B Sync Modal (`itc-shield/page.tsx`)

#### 3.1 Preset Tabs and Custom Range Synchronization
The sync modal provides three intuitive top-level tabs:
1. **FY 2025–26**: Instantly populates `from_period = '042025'` and `to_period = '032026'`.
2. **FY 2026–27**: Instantly populates `from_period = '042026'` and `to_period = '102026'` (up to current active month).
3. **Single Month / Custom Range**: Allows free-form specification of start and end periods.

#### 3.2 Dynamic Live Range Banner
Between the input fields and the action button, the modal dynamically displays a live summary banner:
- When a valid multi-month range is selected:
  ```text
  Selected range: April 2026 – October 2026 (7 return periods)
  ```
- If the user selects an inverted range (`from_period > to_period`):
  ```text
  Invalid range: Start month (October 2026) cannot be later than End month (April 2026).
  ```
  The "Sync Selected Periods" submission button is automatically disabled until the range is corrected.

---

### 4. Component Verification & Test Coverage

The component logic is certified through comprehensive unit tests in `frontend/src/components/ui/month-picker-input.test.ts`:
- Parsing full month name + 4-digit year (`"April 2026"` -> `"042026"`)
- Parsing abbreviated month name + 4-digit year (`"Apr 2026"` -> `"042026"`)
- Parsing numeric 6-digit period (`"042026"` -> `"042026"`)
- Parsing slashed/hyphenated periods (`"04/2026"`, `"2026-04"` -> `"042026"`)
- Correct rejection of invalid strings (`"not-a-month"`, `"132026"`)
- Display label formatting (`"042026"` -> `"April 2026"`).

All 63 frontend unit tests (`npm test`) pass with 0 errors, and TypeScript compilation (`npx tsc --noEmit`) passes with 0 type errors.
