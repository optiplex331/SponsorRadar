import { useCallback, useEffect, useMemo, useState } from "react";
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
import { ThemeToggle } from "./ThemeToggle";

interface Status {
  last_collect_at: string | null;
  sources_ok: number;
  sources_total: number;
  register_updated_on: string | null;
  postings: number;
}

const PAGE = 100;
const REPO_URL = "https://github.com/optiplex331/SponsorRadar";
const REGISTER_URL =
  "https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants";
const FRESH_COLLECT_MS = 30 * 3_600_000;
const SENIORITY_LABEL: Record<Seniority, string> = {
  intern: "Intern",
  junior: "Junior",
  unspecified: "Level not stated",
  senior: "Senior",
};
const MATCH_LABEL: Record<MatchStatus, string> = {
  kvk_confirmed: "KvK confirmed",
  name_inferred: "Likely match",
  unmatched: "Not on register",
};
const MATCH_HINT: Record<MatchStatus, string> = {
  kvk_confirmed: "The employer's KvK number was checked by hand against the IND register.",
  name_inferred: "The employer name matches a register organisation. Check the register before applying.",
  unmatched:
    "The employer itself is not on the IND register. The register also lists payroll and employer-of-record firms, so hiring through one of them may still be possible.",
};
const KM_LABEL: Record<KmState, string> = {
  meets: "Meets the threshold",
  crosses: "Threshold: depends on offer",
  below: "Below the threshold",
};
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

// Kept in the browser: when this browser last opened the page, to mark new postings (and, in
// ThemeToggle, a theme override). Neither leaves the browser, and storage may be blocked, so every access is guarded.
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

/** Filters that differ from the defaults; the salary check is a display choice and does not count. */
function activeFilterCount(f: Filters): number {
  const sameSeniority =
    f.seniority.length === DEFAULTS.seniority.length && f.seniority.every((s) => DEFAULTS.seniority.includes(s));
  return [
    !sameSeniority,
    f.sponsor !== DEFAULTS.sponsor,
    f.hideDutch !== DEFAULTS.hideDutch,
    f.maxYears !== DEFAULTS.maxYears,
    f.showRefusesVisa !== DEFAULTS.showRefusesVisa,
    f.city.trim() !== "",
    f.q.trim() !== "",
  ].filter(Boolean).length;
}

export default function App() {
  const [filters, setFilters] = useState<Filters>(() => readFilters(window.location.search));
  const [postings, setPostings] = useState<Posting[] | null>(null);
  const [status, setStatus] = useState<Status | null | undefined>(undefined); // undefined: loading, null: failed
  const [failed, setFailed] = useState(false);
  const [shown, setShown] = useState(PAGE);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [lastVisit] = useState(readLastVisit);

  useEffect(() => writeLastVisit(Date.now()), []);

  const load = useCallback(() => {
    setFailed(false);
    setPostings(null);
    setStatus(undefined);
    getJson<Posting[]>("/api/postings").then(setPostings, () => setFailed(true));
    getJson<Status>("/api/status").then(setStatus, () => setStatus(null));
  }, []);

  useEffect(load, [load]);

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
  const active = activeFilterCount(filters);
  const reset = () => setFilters({ ...DEFAULTS, km: filters.km });
  const showEmployer = (employer: string, delisted: boolean) => {
    update({ q: employer, ...(delisted ? { sponsor: "all" as const } : {}) });
    window.scrollTo({ top: 0 });
  };

  return (
    <>
      <header className="masthead wrap">
        <div className="masthead-top">
          <h1 className="wordmark">
            <svg className="wordmark-mark" viewBox="0 0 32 32" aria-hidden="true">
              <circle cx="16" cy="16" r="13" />
              <circle cx="16" cy="16" r="7.5" />
              <circle className="wordmark-dot" cx="16" cy="16" r="3" />
            </svg>
            NL Sponsor Radar
          </h1>
          <ThemeToggle />
        </div>
        <p className="lede">Tech jobs in the Netherlands at employers the IND recognises as visa sponsors.</p>
        <StatusLine status={status} />
      </header>

      <div className="wrap layout">
        <main className="main" id="main">
          <section className="panel filter-panel" aria-label="Filters">
            <div className="filter-bar">
              <button
                type="button"
                className="btn filter-toggle"
                aria-expanded={filtersOpen}
                aria-controls="filters"
                onClick={() => setFiltersOpen((o) => !o)}
              >
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path d="M3 5h14M6 10h8M8.5 15h3" />
                </svg>
                Filters
                {active > 0 && (
                  <span className="filter-count">
                    {active}
                    <span className="sr-only"> active</span>
                  </span>
                )}
              </button>
              <p className="count" aria-live="polite">
                {postings === null ? (
                  failed ? (
                    "Postings unavailable"
                  ) : (
                    "Loading postings"
                  )
                ) : (
                  <>
                    <strong>{results.length.toLocaleString("en-GB")}</strong>{" "}
                    {results.length === 1 ? "posting" : "postings"}
                    <span className="count-of"> of {postings.length.toLocaleString("en-GB")}</span>
                  </>
                )}
              </p>
              {!isDefault && (
                <button type="button" className="btn btn-quiet reset" onClick={reset}>
                  Reset
                </button>
              )}
            </div>

            <form
              id="filters"
              className={filtersOpen ? "filters is-open" : "filters"}
              role="search"
              onSubmit={(e) => e.preventDefault()}
            >
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
              <div className="field field-km">
                <label htmlFor="km">Salary vs. visa threshold</label>
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
            {/* Outside the form, which is collapsed on mobile: the reader must see that the list is pre-filtered. */}
            <p className="default-note">
              By default the list shows roles asking for 2 years of experience or less (or not saying), at employers on
              the register, without a Dutch requirement, and hides postings that rule out visa sponsorship or ask for
              existing work rights.
            </p>
          </section>

          {filters.km && (
            <p className="note km-note">
              Salary compared with the IND highly skilled migrant threshold for 2026,{" "}
              {KM_TIER_LABEL[filters.km].toLowerCase()}: <strong>{euro.format(KM_MONTHLY_EUR[filters.km])}</strong> gross
              a month, without holiday allowance. Only postings with a salary in euros per month or year get a mark;
              yearly figures are divided by 12. <a href={KM_SOURCE}>IND required amounts</a>.
            </p>
          )}

          {failed ? (
            <div className="state" role="alert">
              <p>We couldn't load the postings. The server may be restarting or your connection dropped.</p>
              <button type="button" className="btn btn-accent" onClick={load}>
                Try again
              </button>
            </div>
          ) : postings === null ? (
            <ol className="postings" aria-hidden="true">
              {[0, 1, 2, 3].map((i) => (
                <li key={i} className="posting skeleton">
                  <span className="bone bone-title" />
                  <span className="bone bone-line" />
                  <span className="bone bone-meta" />
                </li>
              ))}
            </ol>
          ) : results.length === 0 ? (
            <div className="state">
              <p>No postings match these filters. Widen the level or experience filter, or clear the search.</p>
              {!isDefault && (
                <button type="button" className="link-button" onClick={reset}>
                  Reset filters
                </button>
              )}
            </div>
          ) : (
            <ol className="postings">
              {results.slice(0, shown).map((p) => (
                <PostingCard key={p.id} posting={p} km={filters.km} isNew={isNew(p, lastVisit)} />
              ))}
            </ol>
          )}

          {results.length > shown && (
            <button type="button" className="btn more" onClick={() => setShown((n) => n + PAGE)}>
              Show {Math.min(PAGE, results.length - shown)} more
            </button>
          )}
        </main>

        <aside className="aside" aria-label="IND register">
          <SponsorLookup onShowEmployer={showEmployer} />
          <RegisterChanges onShowEmployer={showEmployer} />
        </aside>
      </div>

      <footer className="wrap footer">
        <section aria-labelledby="about-title">
          <h2 id="about-title">About and method</h2>
          <p>
            Postings come from public Greenhouse, Ashby, and Recruitee job boards. Employers are linked to the{" "}
            <a href={REGISTER_URL}>IND public register</a> of recognised sponsors. The list is collected once a day,
            around 05:00 UTC, and the register is checked on every run.
          </p>
          <dl className="legend">
            <div>
              <dt>
                <MatchBadge status="kvk_confirmed" />
              </dt>
              <dd>The employer's KvK number was checked by hand against the register.</dd>
            </div>
            <div>
              <dt>
                <MatchBadge status="name_inferred" />
              </dt>
              <dd>The employer's name matches a register organisation. Check the register yourself.</dd>
            </div>
            <div>
              <dt>
                <MatchBadge status="unmatched" />
              </dt>
              <dd>The employer itself is not on the register; a payroll or employer-of-record firm may still hire.</dd>
            </div>
          </dl>
          <p>Dutch, experience, and sponsorship hints are read from the posting text and can be wrong.</p>
        </section>
        <section aria-labelledby="privacy-title">
          <h2 id="privacy-title">Privacy</h2>
          <p>
            No cookies and no tracking. Your browser keeps two values in local storage: when you last visited, to mark
            new postings, and your theme choice if you changed it. Neither is sent to us.
          </p>
        </section>
        <section aria-labelledby="disclaimer-title">
          <h2 id="disclaimer-title">Not advice</h2>
          <p>
            This is not legal or immigration advice. Salary checks use the amounts the job board states. Check the{" "}
            <a href={REGISTER_URL}>IND register</a> and the <a href={KM_SOURCE}>IND required amounts</a> before
            applying.
          </p>
          <p>
            <a href={REPO_URL}>Source on GitHub</a>
          </p>
        </section>
      </footer>
    </>
  );
}

function StatusLine({ status }: { status: Status | null | undefined }) {
  if (status === undefined) return <p className="status">Loading collection status</p>;
  if (status === null) return <p className="status">Collection status unavailable</p>;
  const last = status.last_collect_at ? new Date(status.last_collect_at) : null;
  const fresh = last !== null && Date.now() - last.getTime() < FRESH_COLLECT_MS;
  return (
    <dl className="status">
      <div>
        <dt>
          <span className={fresh ? "status-dot" : "status-dot is-stale"} aria-hidden="true" />
          Collected
        </dt>
        <dd>
          {last ? timeFormat.format(last) : "not yet"}
          {last && !fresh && <span className="sr-only"> (more than 30 hours ago)</span>}
        </dd>
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

function MatchBadge({ status }: { status: MatchStatus }) {
  return (
    <span className={`badge match-${status}`} title={MATCH_HINT[status]}>
      {status === "kvk_confirmed" && (
        <svg viewBox="0 0 12 12" aria-hidden="true">
          <path d="M2.5 6.2 5 8.6l4.5-5" />
        </svg>
      )}
      {MATCH_LABEL[status]}
    </span>
  );
}

function PostingCard({ posting: p, km, isNew }: { posting: Posting; km: KmTier | null; isNew: boolean }) {
  const orgs = p.register_organisations;
  const date = p.published_at ?? p.first_seen_at;
  const months = staleMonths(p);
  const salary = formatSalary(p);
  const flag = km ? kmFlag(p, km) : null;
  return (
    <li className="posting">
      <div className="posting-head">
        <h2 className="posting-title">
          <a href={p.url} target="_blank" rel="noopener noreferrer">
            {p.title}
          </a>
        </h2>
        <p className="posting-employer">
          <span className="employer">{p.employer}</span>
          <MatchBadge status={p.match_status} />
          {isNew && <span className="badge badge-new">New</span>}
          {p.sponsorship_stance === "offers" && (
            <span className="badge badge-plain" title="The posting states visa or relocation support.">
              Visa or relocation support
            </span>
          )}
        </p>
      </div>

      {(salary || flag) && (
        <div className="posting-pay">
          {salary && <p className="salary">{salary}</p>}
          {flag && (
            <p className={`km km-${flag.state}`} title={`IND threshold ${euro.format(flag.threshold)} gross a month`}>
              {KM_LABEL[flag.state]}
              {flag.checkHolidayAllowance && <span className="km-check">Check: IND excludes the 8% holiday allowance</span>}
            </p>
          )}
        </div>
      )}

      <ul className="posting-meta" aria-label="Details">
        <li className={p.seniority === "senior" ? "level level-senior" : "level"}>{SENIORITY_LABEL[p.seniority]}</li>
        {p.location && <li>{shortLocation(p.location)}</li>}
        {p.min_years !== null && <li>{p.min_years}+ yrs asked</li>}
        {p.dutch_required && <li className="hint-dutch">Dutch required</li>}
        <li className="date">
          {months === null ? (
            <time dateTime={date}>{formatDay(date)}</time>
          ) : (
            <time dateTime={date} title={fullDayFormat.format(new Date(date))}>
              Posted {postedAgo(months)} ago
            </time>
          )}
        </li>
      </ul>

      {(p.delisted_on || p.match_status === "unmatched" || orgs.length > 0 || p.sponsorship_stance?.startsWith("refuses")) && (
        <div className="posting-notes">
          {p.delisted_on ? (
            <p className="note-warn">Removed from register on {calendarDayFormat.format(new Date(p.delisted_on))}</p>
          ) : (
            p.match_status === "unmatched" && (
              <p>
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
            <p>No relocation support: fine if you already live in the Netherlands.</p>
          )}
          {p.sponsorship_stance === "refuses_visa" && (
            <p className="note-warn">The posting rules out visa sponsorship or asks for existing work rights.</p>
          )}
        </div>
      )}
    </li>
  );
}
