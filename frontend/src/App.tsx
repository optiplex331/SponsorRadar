import { useEffect, useMemo, useState } from "react";
import {
  applyFilters,
  cityOptions,
  DEFAULTS,
  readFilters,
  SENIORITIES,
  shortLocation,
  writeFilters,
  type Filters,
  type MatchStatus,
  type Posting,
  type Seniority,
} from "./filters";

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
  unmatched: "Not on register",
};
const MATCH_HINT: Record<MatchStatus, string> = {
  kvk_confirmed: "The employer's KvK number was checked by hand against the IND register.",
  name_inferred: "The employer name matches a register organisation. Check the register before applying.",
  unmatched: "No register organisation found for this employer.",
};

const dayFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const fullDayFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
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

  const results = useMemo(() => (postings ? applyFilters(postings, filters) : []), [postings, filters]);
  const cities = useMemo(() => (postings ? cityOptions(postings) : []), [postings]);
  const update = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));
  const toggleSeniority = (s: Seniority) =>
    update({
      seniority: filters.seniority.includes(s)
        ? filters.seniority.filter((x) => x !== s)
        : SENIORITIES.filter((x) => x === s || filters.seniority.includes(x)),
    });
  const isDefault = writeFilters(filters) === "";

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
              value={filters.maxYears ?? ""}
              onChange={(e) => update({ maxYears: e.target.value === "" ? null : Number(e.target.value) })}
            >
              <option value="">Any</option>
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
          <label className="toggle">
            <input
              type="checkbox"
              checked={filters.hideDutch}
              onChange={(e) => update({ hideDutch: e.target.checked })}
            />
            <span>Hide jobs that require Dutch</span>
          </label>
        </form>

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
            <button type="button" className="reset" onClick={() => setFilters(DEFAULTS)}>
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
            <PostingRow key={p.id} posting={p} />
          ))}
        </ol>

        {results.length > shown && (
          <button type="button" className="more" onClick={() => setShown((n) => n + PAGE)}>
            Show {Math.min(PAGE, results.length - shown)} more
          </button>
        )}
      </main>

      <footer className="wrap footer">
        <p>
          Postings come from public Greenhouse, Ashby, and Recruitee job boards. Employers are linked to the{" "}
          <a href="https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants">
            IND public register
          </a>{" "}
          automatically. Dutch and experience hints are read from the posting text and can be wrong. No cookies, no
          tracking. <a href="https://github.com/optiplex331/SponsorRadar">Source on GitHub</a>.
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

function PostingRow({ posting: p }: { posting: Posting }) {
  const orgs = p.register_organisations;
  const date = p.published_at ?? p.first_seen_at;
  return (
    <li className="posting">
      <div className="posting-main">
        <h2 className="posting-title">
          <a href={p.url} target="_blank" rel="noopener noreferrer">
            {p.title}
          </a>
        </h2>
        <p className="posting-employer">
          <span className="employer">{p.employer}</span>
          <span className={`match match-${p.match_status}`} title={MATCH_HINT[p.match_status]}>
            {MATCH_LABEL[p.match_status]}
          </span>
        </p>
        {orgs.length > 0 && (
          <p className="register-orgs" title={orgs.join("\n")}>
            Register: {orgs.slice(0, 2).join(", ")}
            {orgs.length > 2 && ` +${orgs.length - 2}`}
          </p>
        )}
      </div>
      <ul className="posting-meta" aria-label="Details">
        <li className={`level level-${p.seniority}`}>{SENIORITY_LABEL[p.seniority]}</li>
        {p.location && <li className="location">{shortLocation(p.location)}</li>}
        {p.min_years !== null && <li className="hint">{p.min_years}+ yrs asked</li>}
        {p.dutch_required && <li className="hint hint-dutch">Dutch required</li>}
        <li className="date">
          <time dateTime={date}>{formatDay(date)}</time>
        </li>
      </ul>
    </li>
  );
}
