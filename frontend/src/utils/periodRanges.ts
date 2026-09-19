export type PeriodPreset = "ALL" | "THIS_MONTH" | "LAST_MONTH" | "THIS_QUARTER" | "TODAY" | "CUSTOM";

export interface PeriodDateRange {
  preset: PeriodPreset;
  startDate: string; // YYYY-MM-DD
  endDate: string;   // YYYY-MM-DD
  label: string;
  formattedRange: string;
}

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
];

function pad(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

export function formatDateToYMD(d: Date): string {
  const y = d.getFullYear();
  const m = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  return `${y}-${m}-${day}`;
}

export function formatFriendlyDate(ymd: string): string {
  if (!ymd) return "";
  const parts = ymd.split("-");
  if (parts.length !== 3) return ymd;
  const year = parts[0];
  const monthIdx = parseInt(parts[1], 10) - 1;
  const day = parseInt(parts[2], 10);
  const monthName = MONTH_NAMES[monthIdx] || parts[1];
  return `${day} ${monthName} ${year}`;
}

export function computePeriodDateRange(
  preset: PeriodPreset,
  fy: { start_date?: string; end_date?: string; code?: string; name?: string } | null,
  customStart?: string,
  customEnd?: string,
  nowDate: Date = new Date()
): PeriodDateRange {
  const fyStart = fy?.start_date || `${nowDate.getFullYear()}-04-01`;
  const fyEnd = fy?.end_date || `${nowDate.getFullYear() + 1}-03-31`;

  const curYear = nowDate.getFullYear();
  const curMonth1 = nowDate.getMonth() + 1; // 1 to 12

  if (preset === "ALL") {
    const fyLabel = fy?.name || (fy?.code ? `FY ${fy.code}` : "Full Financial Year");
    return {
      preset: "ALL",
      startDate: fyStart,
      endDate: fyEnd,
      label: fyLabel,
      formattedRange: `${formatFriendlyDate(fyStart)} – ${formatFriendlyDate(fyEnd)}`,
    };
  }

  if (preset === "TODAY") {
    const todayStr = formatDateToYMD(nowDate);
    return {
      preset: "TODAY",
      startDate: todayStr,
      endDate: todayStr,
      label: "Today",
      formattedRange: formatFriendlyDate(todayStr),
    };
  }

  if (preset === "THIS_MONTH") {
    const start = `${curYear}-${pad(curMonth1)}-01`;
    const lastDay = new Date(curYear, curMonth1, 0).getDate();
    const end = `${curYear}-${pad(curMonth1)}-${pad(lastDay)}`;
    const monthName = MONTH_NAMES[curMonth1 - 1];
    return {
      preset: "THIS_MONTH",
      startDate: start,
      endDate: end,
      label: `This Month (${monthName})`,
      formattedRange: `${formatFriendlyDate(start)} – ${formatFriendlyDate(end)}`,
    };
  }

  if (preset === "LAST_MONTH") {
    let lastMonth = curMonth1 - 1;
    let year = curYear;
    if (lastMonth === 0) {
      lastMonth = 12;
      year -= 1;
    }
    const start = `${year}-${pad(lastMonth)}-01`;
    const lastDay = new Date(year, lastMonth, 0).getDate();
    const end = `${year}-${pad(lastMonth)}-${pad(lastDay)}`;
    const monthName = MONTH_NAMES[lastMonth - 1];
    return {
      preset: "LAST_MONTH",
      startDate: start,
      endDate: end,
      label: `Last Month (${monthName})`,
      formattedRange: `${formatFriendlyDate(start)} – ${formatFriendlyDate(end)}`,
    };
  }

  if (preset === "THIS_QUARTER") {
    // Indian Financial Quarters:
    // Q1: Apr-Jun (4, 5, 6)
    // Q2: Jul-Sep (7, 8, 9)
    // Q3: Oct-Dec (10, 11, 12)
    // Q4: Jan-Mar (1, 2, 3)
    let qNumber = 1;
    let startMonth = 4;
    let endMonth = 6;
    let qYear = curYear;

    if (curMonth1 >= 4 && curMonth1 <= 6) {
      qNumber = 1;
      startMonth = 4;
      endMonth = 6;
      qYear = curYear;
    } else if (curMonth1 >= 7 && curMonth1 <= 9) {
      qNumber = 2;
      startMonth = 7;
      endMonth = 9;
      qYear = curYear;
    } else if (curMonth1 >= 10 && curMonth1 <= 12) {
      qNumber = 3;
      startMonth = 10;
      endMonth = 12;
      qYear = curYear;
    } else {
      qNumber = 4;
      startMonth = 1;
      endMonth = 3;
      qYear = curYear;
    }

    const start = `${qYear}-${pad(startMonth)}-01`;
    const lastDay = new Date(qYear, endMonth, 0).getDate();
    const end = `${qYear}-${pad(endMonth)}-${pad(lastDay)}`;

    return {
      preset: "THIS_QUARTER",
      startDate: start,
      endDate: end,
      label: `This Quarter (Q${qNumber})`,
      formattedRange: `${formatFriendlyDate(start)} – ${formatFriendlyDate(end)}`,
    };
  }

  // CUSTOM
  const start = customStart || fyStart;
  const end = customEnd || formatDateToYMD(nowDate);
  return {
    preset: "CUSTOM",
    startDate: start,
    endDate: end,
    label: "Custom Range",
    formattedRange: `${formatFriendlyDate(start)} – ${formatFriendlyDate(end)}`,
  };
}
