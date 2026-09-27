// IND highly skilled migrant (kennismigrant) salary thresholds, gross per month without holiday allowance.
// Source: https://ind.nl/en/required-amounts-income-requirements ("Application to work as a highly skilled
// migrant"), amounts for 2026, valid from 1 January 2026. IND changes them every 1 January: check again then.
export const KM_SOURCE = "https://ind.nl/en/required-amounts-income-requirements";
export const KM_EFFECTIVE = "2026-01-01";

export type KmTier = "graduate" | "under30" | "30plus";
export const KM_TIERS: KmTier[] = ["graduate", "under30", "30plus"];

export const KM_MONTHLY_EUR: Record<KmTier, number> = {
  graduate: 3122, // reduced salary criterion: during or after the orientation year (zoekjaar), or recent graduate
  under30: 4357,
  "30plus": 5942,
};

export const KM_TIER_LABEL: Record<KmTier, string> = {
  graduate: "Recent graduate (reduced)",
  under30: "Under 30",
  "30plus": "30 or older",
};

export type SalaryPeriod = "year" | "month" | "hour";

export interface Salary {
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: SalaryPeriod | null;
}

export type KmState = "meets" | "crosses" | "below";

export interface KmFlag {
  state: KmState;
  threshold: number;
  // Yearly figures may or may not include the 8% holiday allowance, which IND does not count.
  checkHolidayAllowance: boolean;
}

/** Compare a posting's salary with the monthly threshold. Only EUR monthly or yearly salaries are compared. */
export function kmFlag(salary: Salary, tier: KmTier): KmFlag | null {
  const { salary_currency: currency, salary_period: period } = salary;
  if (currency !== "EUR" || (period !== "month" && period !== "year")) return null;
  // A single stated value counts as both ends of the range.
  const low = salary.salary_min ?? salary.salary_max;
  const high = salary.salary_max ?? salary.salary_min;
  if (low === null || high === null) return null;
  const perMonth = period === "year" ? 1 / 12 : 1;
  const threshold = KM_MONTHLY_EUR[tier];
  const state: KmState =
    low * perMonth >= threshold ? "meets" : high * perMonth >= threshold ? "crosses" : "below";
  return { state, threshold, checkHolidayAllowance: period === "year" };
}

export function readKmTier(search: string): KmTier | null {
  const value = new URLSearchParams(search).get("km");
  return KM_TIERS.find((t) => t === value) ?? null;
}

const PERIOD_LABEL: Record<SalaryPeriod, string> = { year: "year", month: "month", hour: "hour" };

/** "€4,000–5,500 / month"; null when the posting states no amount. */
export function formatSalary(s: Salary): string | null {
  const low = s.salary_min ?? s.salary_max;
  const high = s.salary_max ?? s.salary_min;
  if (low === null || high === null) return null;
  let money: (n: number) => string;
  try {
    const f = new Intl.NumberFormat("en-GB", { style: "currency", currency: s.salary_currency ?? "", maximumFractionDigits: 0 });
    money = (n) => f.format(n);
  } catch {
    money = (n) => `${s.salary_currency ?? ""} ${Math.round(n).toLocaleString("en-GB")}`.trim();
  }
  const plain = (n: number) => Math.round(n).toLocaleString("en-GB");
  const amount = low === high ? money(low) : `${money(low)}–${plain(high)}`;
  return s.salary_period ? `${amount} / ${PERIOD_LABEL[s.salary_period]}` : amount;
}
