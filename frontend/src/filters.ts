export type Seniority = "intern" | "junior" | "unspecified" | "senior";
export type MatchStatus = "kvk_confirmed" | "name_inferred" | "unmatched";

export interface Posting {
  id: number;
  title: string;
  url: string;
  location: string;
  department: string | null;
  published_at: string | null;
  first_seen_at: string;
  seniority: Seniority;
  dutch_required: boolean;
  min_years: number | null;
  employer: string;
  match_status: MatchStatus;
  register_organisations: string[];
}

export interface Filters {
  seniority: Seniority[];
  sponsor: "matched" | "all";
  hideDutch: boolean;
  maxYears: number | null;
  city: string;
  q: string;
}

export const SENIORITIES: Seniority[] = ["intern", "junior", "unspecified", "senior"];
export const DEFAULTS: Filters = {
  seniority: ["intern", "junior", "unspecified"],
  sponsor: "matched",
  hideDutch: true,
  maxYears: null,
  city: "",
  q: "",
};

// Query params double as saved filters (phase 5 RSS reuses them), so only non-defaults are written.
export function readFilters(search: string): Filters {
  const p = new URLSearchParams(search);
  const years = Number.parseInt(p.get("years") ?? "", 10);
  const seniority = p.get("seniority");
  return {
    seniority:
      seniority === null
        ? DEFAULTS.seniority
        : SENIORITIES.filter((s) => seniority.split(",").includes(s)),
    sponsor: p.get("sponsor") === "all" ? "all" : "matched",
    hideDutch: p.get("dutch") !== "show",
    maxYears: Number.isFinite(years) && years >= 0 ? years : null,
    city: p.get("city") ?? "",
    q: p.get("q") ?? "",
  };
}

export function writeFilters(f: Filters): string {
  const p = new URLSearchParams();
  const sameSeniority =
    f.seniority.length === DEFAULTS.seniority.length && f.seniority.every((s) => DEFAULTS.seniority.includes(s));
  if (!sameSeniority) p.set("seniority", f.seniority.join(","));
  if (f.sponsor === "all") p.set("sponsor", "all");
  if (!f.hideDutch) p.set("dutch", "show");
  if (f.maxYears !== null) p.set("years", String(f.maxYears));
  if (f.city.trim()) p.set("city", f.city.trim());
  if (f.q.trim()) p.set("q", f.q.trim());
  const query = p.toString();
  return query ? `?${query}` : "";
}

const fold = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();

export function applyFilters(postings: Posting[], f: Filters): Posting[] {
  const words = fold(f.q).split(/\s+/).filter(Boolean);
  const city = fold(f.city.trim());
  return postings.filter((p) => {
    if (!f.seniority.includes(p.seniority)) return false;
    if (f.sponsor === "matched" && p.match_status === "unmatched") return false;
    if (f.hideDutch && p.dutch_required) return false;
    // Unknown years stay visible: the rules only read explicit numbers.
    if (f.maxYears !== null && p.min_years !== null && p.min_years > f.maxYears) return false;
    if (city && !fold(p.location).includes(city)) return false;
    if (words.length) {
      const haystack = fold(`${p.title} ${p.employer} ${p.department ?? ""}`);
      if (!words.every((w) => haystack.includes(w))) return false;
    }
    return true;
  });
}

const NOT_A_CITY = new Set([
  "netherlands", "the netherlands", "nederland", "nl", "remote", "remote job", "hybrid", "europe", "emea",
]);

const NL_REGIONS = new Set([
  "netherlands", "the netherlands", "nederland", "nl", "noord-holland", "north holland", "zuid-holland",
  "south holland", "utrecht", "noord-brabant", "north brabant", "gelderland", "overijssel", "flevoland",
  "groningen", "friesland", "fryslan", "drenthe", "zeeland", "limburg",
]);

const isDutchPart = (segments: string[]) =>
  segments.length === 1 || NL_REGIONS.has(fold(segments[segments.length - 1]));

/** Long multi-office locations shrink to their Dutch parts plus a count of the rest. */
export function shortLocation(location: string): string {
  const parts = location.split(";").map((part) => part.trim()).filter(Boolean);
  if (parts.length <= 2) return parts.join("; ");
  const dutch = parts.filter((part) => isDutchPart(part.split(",").map((s) => s.trim()))).slice(0, 2);
  const kept = dutch.length ? dutch : parts.slice(0, 1);
  return `${kept.join("; ")} +${parts.length - kept.length} more`;
}

/** Most frequent place names: the first part of each ";"-separated location whose region is Dutch. */
export function cityOptions(postings: Posting[], limit = 40): string[] {
  const counts = new Map<string, number>();
  for (const p of postings) {
    for (const part of p.location.split(";")) {
      const segments = part.split(",").map((s) => s.trim());
      const name = segments[0];
      if (!isDutchPart(segments)) continue;
      if (!name || NOT_A_CITY.has(name.toLowerCase()) || /\d/.test(name)) continue;
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .filter(([, n]) => n > 1)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([name]) => name);
}
