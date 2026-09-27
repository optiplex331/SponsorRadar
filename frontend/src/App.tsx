import { useEffect, useMemo, useState } from "react";
import {
  applyFilters,
  cityOptions,
  DEFAULTS,
  freshFirst,
  isDefaultView,
  isNew,
  postedAgo,
  readFilters,
  SENIORITIES,
  shortLocation,
  staleMonths,
  writeFilters,
  type Filters,
  type MatchStatus,
  type Posting,
  type Seniority,
} from "./filters";
import {
  formatSalary,
  KM_MONTHLY_EUR,
  KM_SOURCE,
  KM_TIER_LABEL,
  KM_TIERS,
  kmFlag,
  type KmState,
  type KmTier,
} from "./km";
import { RegisterChanges } from "./RegisterChanges";
import { SponsorLookup } from "./SponsorLookup";

interface Status {
  last_collect_at: string | null;
  sources_ok: number;
  sources_total: number;
  register_updated_on: string | null;
  postings: number;
}

const PAGE = 100;
const SENIORITY_LABEL: Record<Seniority, string> = {
  intern: "Intern",
  junior: "Junior",
  unspecified: "Level not stated",
  senior: "Senior",
};
const MATCH_LABEL: Record<MatchStatus, string> = {
  kvk_confirmed: "KvK confirmed",
  name_inferred: "Name match",
  unmatched: "Employer not on register",
};
const MATCH_HINT: Record<MatchStatus, string> = {
  kvk_confirmed: "The employer's KvK number was checked by hand against the IND register.",
  name_inferred: "The employer name matches a register organisation. Check the register before applying.",
  unmatched:
    "The employer itself is not on the IND register. The register also lists payroll and employer-of-record firms, so hiring through one of them may still be possible.",
};
const KM_LABEL: Record<KmState, string> = {
  meets: "Meets KM salary",
  crosses: "KM salary: depends on offer",
  below: "Below KM salary",
};
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

// The one thing kept in the browser: when this browser last opened the page, to mark new postings.
// It never leaves the browser, and storage may be blocked, so every access is guarded.
const LAST_VISIT_KEY = "lastVisit";

function readLastVisit(): number | null {
  try {
    const value = Number(window.localStorage.getItem(LAST_VISIT_KEY));
    return value > 0 ? value : null;
  } catch {
    return null;
  }
}

function writeLastVisit(now: number): void {
  try {
    window.localStorage.setItem(LAST_VISIT_KEY, String(now));
  } catch {
    // Private mode or blocked storage: no "new" marks next time, nothing else changes.
  }
}

const dayFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const fullDayFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
// `delisted_on` is a calendar day, so it is formatted in UTC; timestamps above use the visitor's zone.
const calendarDayFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const timeFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
});

function formatDay(iso: string): string {
  const d = new Date(iso);
  return d.getFullYear() === new Date().getFullYear() ? dayFormat.format(d) : fullDayFormat.format(d);
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json() as Promise<T>;
}

export default function App() {
  const [filters, setFilters] = useState<Filters>(() => readFilters(window.location.search));
  const [postings, setPostings] = useState<Posting[] | null>(null);
  const [status, setStatus] = useState<Status | null | undefined>(undefined); // undefined: loading, null: failed
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState(PAGE);
  const [lastVisit] = useState(readLastVisit);

  useEffect(() => writeLastVisit(Date.now()), []);

  useEffect(() => {
    getJson<Posting[]>("/api/postings").then(setPostings, () =>
      setError("We couldn't load the postings. Refresh the page to try again."),
    );
    getJson<Status>("/api/status").then(setStatus, () => setStatus(null));
  }, []);

  useEffect(() => {
    const url = `${window.location.pathname}${writeFilters(filters)}`;
    window.history.replaceState(null, "", url);
    setShown(PAGE);
  }, [filters]);

  const results = useMemo(() => (postings ? freshFirst(applyFilters(postings, filters)) : []), [postings, filters]);
  const cities = useMemo(() => (postings ? cityOptions(postings) : []), [postings]);
  const update = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));
  const toggleSeniority = (s: Seniority) =>
    update({
      seniority: filters.seniority.includes(s)
        ? filters.seniority.filter((x) => x !== s)
        : SENIORITIES.filter((x) => x === s || filters.seniority.includes(x)),
    });
  const isDefault = isDefaultView(filters);
  const showEmployer = (employer: string, delisted: boolean) => {
    update({ q: employer, ...(delisted ? { sponsor: "all" as const } : {}) });
    window.scrollTo({ top: 0 });
  };

  return (
    <>
      <header className="masthead">
        <div className="wrap">
          <h1 className="wordmark">
            <span className="wordmark-dot" aria-hidden="true" />
            NL Sponsor Radar
          </h1>
          <p className="lede">
            Tech jobs in the Netherlands at employers on the IND register of recognised sponsors for the
            highly skilled migrant permit.
          </p>
          <p className="default-note">
            By default the list shows roles asking for 2 years of experience or less (or not saying), at employers on
            the register, without a Dutch requirement, and hides postings that rule out visa sponsorship or ask for existing work rights.
          </p>
          <StatusLine status={status} />
        </div>
      </header>

      <main className="wrap">
        <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
          <div className="field field-q">
            <label htmlFor="q">Role or employer</label>
            <input
              id="q"
              type="search"
              placeholder="backend, data, Adyen"
              value={filters.q}
              onChange={(e) => update({ q: e.target.value })}
            />
          </div>
          <div className="field field-city">
            <label htmlFor="city">City</label>
            <input
              id="city"
              type="search"
              list="city-options"
              placeholder="Any city"
              value={filters.city}
              onChange={(e) => update({ city: e.target.value })}
            />
            <datalist id="city-options">
              {cities.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>
          <div className="field field-years">
            <label htmlFor="years">Experience asked</label>
            <select
              id="years"
              value={filters.maxYears ?? "any"}
              onChange={(e) => update({ maxYears: e.target.value === "any" ? null : Number(e.target.value) })}
            >
              <option value="any">Any</option>
              {[0, 1, 2, 3, 5].map((n) => (
                <option key={n} value={n}>
                  {n === 0 ? "No experience" : `Up to ${n} ${n === 1 ? "year" : "years"}`}
                </option>
              ))}
            </select>
          </div>
          <div className="field field-sponsor">
            <label htmlFor="sponsor">Employers</label>
            <select
              id="sponsor"
              value={filters.sponsor}
              onChange={(e) => update({ sponsor: e.target.value as Filters["sponsor"] })}
            >
              <option value="matched">On IND register</option>
              <option value="all">All employers</option>
            </select>
          </div>
          <fieldset className="field field-seniority">
            <legend>Level</legend>
            <div className="chips">
              {SENIORITIES.map((s) => (
                <label key={s} className="chip">
                  <input
                    type="checkbox"
                    checked={filters.seniority.includes(s)}
                    onChange={() => toggleSeniority(s)}
                  />
                  <span>{SENIORITY_LABEL[s]}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="field field-km">
            <label htmlFor="km">KM salary check</label>
            <select
              id="km"
              value={filters.km ?? ""}
              onChange={(e) => update({ km: (e.target.value || null) as KmTier | null })}
            >
              <option value="">Off</option>
              {KM_TIERS.map((t) => (
                <option key={t} value={t}>
                  {KM_TIER_LABEL[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="toggles">
            <label className="toggle">
              <input
                type="checkbox"
                checked={filters.hideDutch}
                onChange={(e) => update({ hideDutch: e.target.checked })}
              />
              <span>Hide jobs that require Dutch</span>
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={!filters.showRefusesVisa}
                onChange={(e) => update({ showRefusesVisa: !e.target.checked })}
              />
              <span>Hide jobs that rule out visa sponsorship or need existing work rights</span>
            </label>
          </div>
        </form>

        {filters.km && (
          <p className="km-note">
            Salary check against the IND highly skilled migrant threshold for 2026, {KM_TIER_LABEL[filters.km].toLowerCase()}:{" "}
            <strong>{euro.format(KM_MONTHLY_EUR[filters.km])}</strong> gross a month, without holiday allowance. Only
            postings with a salary in euros per month or year get a mark; yearly figures are divided by 12.{" "}
            <a href={KM_SOURCE}>IND required amounts</a>.
          </p>
        )}

        <div className="results-bar">
          <p className="count" aria-live="polite">
            {postings === null && !error ? (
              "Loading postings"
            ) : (
              <>
                <strong>{results.length.toLocaleString("en-GB")}</strong>{" "}
                {results.length === 1 ? "posting" : "postings"}
                {postings && <span className="count-of"> of {postings.length.toLocaleString("en-GB")}</span>}
              </>
            )}
          </p>
          {!isDefault && (
            <button type="button" className="reset" onClick={() => setFilters({ ...DEFAULTS, km: filters.km })}>
              Reset filters
            </button>
          )}
        </div>

        {error && <p className="notice">{error}</p>}
        {postings && results.length === 0 && (
          <p className="notice">No postings match these filters. Widen the level or experience filter.</p>
        )}

        <ol className="postings">
          {results.slice(0, shown).map((p) => (
            <PostingRow key={p.id} posting={p} km={filters.km} isNew={isNew(p, lastVisit)} />
          ))}
        </ol>

        {results.length > shown && (
          <button type="button" className="more" onClick={() => setShown((n) => n + PAGE)}>
            Show {Math.min(PAGE, results.length - shown)} more
          </button>
        )}

        <SponsorLookup onShowEmployer={showEmployer} />

        <RegisterChanges onShowEmployer={showEmployer} />
      </main>

      <footer className="wrap footer">
        <p>
          Postings come from public Greenhouse, Ashby, and Recruitee job boards. Employers are linked to the{" "}
          <a href="https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants">
            IND public register
          </a>{" "}
          automatically. Dutch, experience, and sponsorship hints are read from the posting text and can be wrong. Salary
          checks use the amounts the job board states and are not advice; check the{" "}
          <a href={KM_SOURCE}>IND required amounts</a> before applying. No cookies, no tracking: your browser only
          remembers when you last visited, to mark new postings, and never sends it to us. <a href="https://github.com/optiplex331/SponsorRadar">Source on GitHub</a>.
        </p>
      </footer>
    </>
  );
}

function StatusLine({ status }: { status: Status | null | undefined }) {
  if (status === undefined) return <p className="status">Loading collection status</p>;
  if (status === null) return <p className="status">Collection status unavailable</p>;
  return (
    <dl className="status">
      <div>
        <dt>Collected</dt>
        <dd>{status.last_collect_at ? timeFormat.format(new Date(status.last_collect_at)) : "not yet"}</dd>
      </div>
      <div>
        <dt>Job boards ok</dt>
        <dd>
          {status.sources_ok}/{status.sources_total}
        </dd>
      </div>
      <div>
        <dt>IND register</dt>
        <dd>{status.register_updated_on ? formatDay(status.register_updated_on) : "unknown"}</dd>
      </div>
    </dl>
  );
}

function PostingRow({ posting: p, km, isNew }: { posting: Posting; km: KmTier | null; isNew: boolean }) {
  const orgs = p.register_organisations;
  const date = p.published_at ?? p.first_seen_at;
  const months = staleMonths(p);
  const salary = formatSalary(p);
  const flag = km ? kmFlag(p, km) : null;
  return (
    <li className="posting">
      <div className="posting-main">
        <h2 className="posting-title">
          {isNew && <span className="new-mark">New</span>}
          <a href={p.url} target="_blank" rel="noopener noreferrer">
            {p.title}
          </a>
        </h2>
        <p className="posting-employer">
          <span className="employer">{p.employer}</span>
          <span className={`match match-${p.match_status}`} title={MATCH_HINT[p.match_status]}>
            {MATCH_LABEL[p.match_status]}
          </span>
          {p.sponsorship_stance === "offers" && (
            <span className="stance-offers" title="The posting states visa or relocation support.">
              Visa or relocation support
            </span>
          )}
        </p>
        {p.delisted_on ? (
          <p className="register-note">Removed from register on {calendarDayFormat.format(new Date(p.delisted_on))}</p>
        ) : (
          p.match_status === "unmatched" && (
            <p className="register-note">
              Employer itself is not on the register; hiring through a payroll or employer-of-record firm may still be
              possible.
            </p>
          )
        )}
        {orgs.length > 0 && (
          <p className="register-orgs" title={orgs.join("\n")}>
            Register: {orgs.slice(0, 2).join(", ")}
            {orgs.length > 2 && ` +${orgs.length - 2}`}
          </p>
        )}
        {p.sponsorship_stance === "refuses_relocation" && (
          <p className="stance-note">No relocation support: fine if you already live in the Netherlands.</p>
        )}
        {p.sponsorship_stance === "refuses_visa" && (
          <p className="stance-note stance-refuses">The posting rules out visa sponsorship or asks for existing work rights.</p>
        )}
      </div>
      <ul className="posting-meta" aria-label="Details">
        <li className={`level level-${p.seniority}`}>{SENIORITY_LABEL[p.seniority]}</li>
        {p.location && <li className="location">{shortLocation(p.location)}</li>}
        {p.min_years !== null && <li className="hint">{p.min_years}+ yrs asked</li>}
        {p.dutch_required && <li className="hint hint-dutch">Dutch required</li>}
        {salary && <li className="salary">{salary}</li>}
        {flag && (
          <li className={`km km-${flag.state}`} title={`IND threshold ${euro.format(flag.threshold)} gross a month`}>
            {KM_LABEL[flag.state]}
            {flag.checkHolidayAllowance && <span className="km-check">check: IND excludes the 8% holiday allowance</span>}
          </li>
        )}
        <li className={months === null ? "date" : "date date-stale"}>
          {months === null ? (
            <time dateTime={date}>{formatDay(date)}</time>
          ) : (
            <time dateTime={date} title={fullDayFormat.format(new Date(date))}>
              Posted {postedAgo(months)} ago
            </time>
          )}
        </li>
      </ul>
    </li>
  );
}
