import { KM_TIER_LABEL, readKmTier, type KmTier, type Salary } from "./km";

export type Seniority = "intern" | "junior" | "unspecified" | "senior";
export type MatchStatus = "kvk_confirmed" | "name_inferred" | "unmatched";
export type Stance = "offers" | "refuses_visa" | "refuses_relocation" | "silent";

export interface Posting extends Salary {
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
  sponsorship_stance: Stance | null;
  // Set when the employer's register entry disappeared; absent from older APIs, so read it as optional.
  delisted_on?: string | null;
}

export interface Filters {
  seniority: Seniority[];
  sponsor: "matched" | "all";
  hideDutch: boolean;
  // Postings that state no years always stay visible; null shows every posting.
  maxYears: number | null;
  showRefusesVisa: boolean;
  city: string;
  q: string;
  // Salary check tier; a display choice kept in the URL, not a filter.
  km: KmTier | null;
}

export const SENIORITIES: Seniority[] = ["intern", "junior", "unspecified", "senior"];
export const DEFAULTS: Filters = {
  seniority: ["intern", "junior", "unspecified"],
  sponsor: "matched",
  hideDutch: true,
  maxYears: 2,
  showRefusesVisa: false,
  city: "",
  q: "",
  km: null,
};

// Query params double as saved filters (phase 5 RSS reuses them), so only non-defaults are written.
export function readFilters(search: string): Filters {
  const p = new URLSearchParams(search);
  const yearsParam = p.get("years");
  const years = Number.parseInt(yearsParam ?? "", 10);
  const seniority = p.get("seniority");
  return {
    seniority:
      seniority === null
        ? DEFAULTS.seniority
        : SENIORITIES.filter((s) => seniority.split(",").includes(s)),
    sponsor: p.get("sponsor") === "all" ? "all" : "matched",
    hideDutch: p.get("dutch") !== "show",
    maxYears: yearsParam === "any" ? null : Number.isFinite(years) && years >= 0 ? years : DEFAULTS.maxYears,
    showRefusesVisa: p.get("visa") === "show",
    city: p.get("city") ?? "",
    q: p.get("q") ?? "",
    km: readKmTier(search),
  };
}

export function writeFilters(f: Filters): string {
  const p = new URLSearchParams();
  const sameSeniority =
    f.seniority.length === DEFAULTS.seniority.length && f.seniority.every((s) => DEFAULTS.seniority.includes(s));
  if (!sameSeniority) p.set("seniority", f.seniority.join(","));
  if (f.sponsor === "all") p.set("sponsor", "all");
  if (!f.hideDutch) p.set("dutch", "show");
  if (f.maxYears !== DEFAULTS.maxYears) p.set("years", f.maxYears === null ? "any" : String(f.maxYears));
  if (f.showRefusesVisa) p.set("visa", "show");
  if (f.city.trim()) p.set("city", f.city.trim());
  if (f.q.trim()) p.set("q", f.q.trim());
  if (f.km) p.set("km", f.km);
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
    if (!f.showRefusesVisa && p.sponsorship_stance === "refuses_visa") return false;
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

/** True when only the salary-check tier differs from the defaults: the reset button leaves the tier alone. */
export function isDefaultView(f: Filters): boolean {
  return writeFilters({ ...f, km: null }) === "";
}

const DAY_MS = 86_400_000;
export const STALE_DAYS = 90;

/** Whole months since the posting went up, or null while it is fresher than STALE_DAYS. */
export function staleMonths(p: Posting, now: number = Date.now()): number | null {
  const days = (now - Date.parse(p.published_at ?? p.first_seen_at)) / DAY_MS;
  return days > STALE_DAYS ? Math.round(days / 30.44) : null;
}

/** "3 months", or whole years from two years on: some boards keep postings open since 2020. */
export function postedAgo(months: number): string {
  return months < 24 ? `${months} months` : `${Math.floor(months / 12)} years`;
}

/** Fresh postings first, stale ones after; the API's newest-first order is kept within each group. */
export function freshFirst(postings: Posting[], now: number = Date.now()): Posting[] {
  const fresh = postings.filter((p) => staleMonths(p, now) === null);
  return fresh.length === postings.length ? postings : [...fresh, ...postings.filter((p) => staleMonths(p, now) !== null)];
}

/** New since the last visit; nothing is new on a first visit. */
export function isNew(p: Posting, lastVisit: number | null): boolean {
  return lastVisit !== null && Date.parse(p.first_seen_at) > lastVisit;
}

const NOT_A_CITY = new Set([
  "netherlands", "the netherlands", "nederland", "nl", "remote", "remote job", "hybrid", "europe", "emea",
]);

const NL_REGIONS = new Set([
  "netherlands", "the netherlands", "nederland", "nl", "noord-holland", "north holland", "zuid-holland",
  "south holland", "utrecht", "noord-brabant", "north brabant", "gelderland", "overijssel", "flevoland",
  "groningen", "friesland", "fryslan", "drenthe", "zeeland", "limburg",
]);

const NL_COUNTRY = new Set(["netherlands", "the netherlands", "nederland", "nl"]);

const isDutchPart = (segments: string[]) =>
  segments.length === 1 || NL_REGIONS.has(fold(segments[segments.length - 1]));

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

const segmentsOf = (part: string) => part.split(",").map((s) => s.trim()).filter(Boolean);
// A region or the country named in the part itself, not just a bare place name.
const namesNL = (segments: string[]) =>
  segments.length > 1 && (NL_REGIONS.has(fold(segments[segments.length - 1])) || segments.some((s) => NL_COUNTRY.has(fold(s))));

/** Bare place names ("Amsterdam") that some posting pairs with a Dutch region or the country. */
export function dutchPlaces(postings: Posting[]): Set<string> {
  const places = new Set<string>();
  for (const p of postings) {
    for (const part of p.location.split(";")) {
      const segments = segmentsOf(part);
      if (namesNL(segments)) places.add(fold(segments[0]));
    }
  }
  return places;
}

/**
 * Short place label for a row: the Dutch parts of the location, each cut to its first comma segment when that
 * segment is a place name. "Amsterdam, Noord-Holland, Netherlands" becomes "Amsterdam"; "France, Remote; Spain,
 * Remote; The Netherlands, Remote" becomes "The Netherlands, Remote". A bare name counts as Dutch when `known`
 * (from dutchPlaces) has it, so "London; Amsterdam" becomes "Amsterdam". The full string belongs in a title.
 */
export function cityLabel(location: string, known: Set<string> = new Set()): string {
  const parts = location.split(";").map(segmentsOf).filter((segments) => segments.length > 0);
  const dutch = parts.filter((segments) => namesNL(segments) || (segments.length === 1 && known.has(fold(segments[0]))));
  const bare = parts.filter((segments) => segments.length === 1);
  const kept = dutch.length ? dutch : bare.length ? bare : parts.slice(0, 1);
  const labels: string[] = [];
  for (const segments of kept) {
    const first = segments[0];
    const place = NOT_A_CITY.has(fold(first)) || NL_REGIONS.has(fold(first)) ? segments.join(", ") : first;
    if (!labels.includes(place)) labels.push(place);
  }
  return labels.slice(0, 2).join("; ");
}

// Legal forms and regional words that brand names and register entries add or drop.
const ENTITY_NOISE = new Set([
  "bv", "nv", "gmbh", "ltd", "holding", "group", "groep", "netherlands", "nederland", "nl", "europe", "benelux",
  "international",
]);

function entityKey(name: string): string {
  return fold(name)
    .replace(/[.,'’()]/g, "")
    .split(/[^a-z0-9]+/)
    .filter((word) => word && !ENTITY_NOISE.has(word))
    .join("");
}

/** True when a register organisation is the employer under its legal name ("Adyen" and "Adyen N.V."). */
export function sameEntity(employer: string, organisation: string): boolean {
  const a = entityKey(employer);
  const b = entityKey(organisation);
  // A prefix only counts for names long enough not to be a common word start ("pay" is not "Payconiq").
  return a !== "" && (a === b || (a.length >= 5 && b.startsWith(a)));
}

export type ChipKey = "years" | "level" | "sponsor" | "dutch" | "visa" | "city" | "q" | "km";

export interface FilterChip {
  key: ChipKey;
  label: string;
}

const LEVEL_WORD: Record<Seniority, string> = {
  intern: "Intern",
  junior: "Junior",
  unspecified: "not stated",
  senior: "Senior",
};

/** Every filter that narrows the list, defaults included, so the reader sees that the default view is filtered. */
export function narrowingChips(f: Filters): FilterChip[] {
  const chips: FilterChip[] = [];
  if (f.maxYears !== null) {
    const n = f.maxYears;
    chips.push({
      key: "years",
      label: n === 0 ? "No experience or not stated" : `Up to ${n} ${n === 1 ? "yr" : "yrs"} or not stated`,
    });
  }
  if (f.seniority.length < SENIORITIES.length) {
    const onlySeniorOff = f.seniority.length === SENIORITIES.length - 1 && !f.seniority.includes("senior");
    const kept = SENIORITIES.filter((s) => f.seniority.includes(s)).map((s) => LEVEL_WORD[s]);
    chips.push({
      key: "level",
      label: onlySeniorOff ? "Excludes senior" : `Level: ${kept.length ? kept.join(", ") : "none"}`,
    });
  }
  if (f.sponsor === "matched") chips.push({ key: "sponsor", label: "On IND register" });
  if (f.hideDutch) chips.push({ key: "dutch", label: "No Dutch requirement" });
  if (!f.showRefusesVisa) chips.push({ key: "visa", label: "Sponsorship not ruled out" });
  if (f.city.trim()) chips.push({ key: "city", label: `City: ${f.city.trim()}` });
  if (f.q.trim()) chips.push({ key: "q", label: `"${f.q.trim()}"` });
  if (f.km) {
    const tier = KM_TIER_LABEL[f.km];
    chips.push({ key: "km", label: `Salary check: ${tier.charAt(0).toLowerCase()}${tier.slice(1)}` });
  }
  return chips;
}

/** The filters with one chip removed: that filter goes to its widest setting. */
export function relaxFilter(f: Filters, key: ChipKey): Filters {
  switch (key) {
    case "years":
      return { ...f, maxYears: null };
    case "level":
      return { ...f, seniority: [...SENIORITIES] };
    case "sponsor":
      return { ...f, sponsor: "all" };
    case "dutch":
      return { ...f, hideDutch: false };
    case "visa":
      return { ...f, showRefusesVisa: true };
    case "city":
      return { ...f, city: "" };
    case "q":
      return { ...f, q: "" };
    case "km":
      return { ...f, km: null };
  }
}
