import { FunnelSimple, MagnifyingGlass, MapPin, X } from "@phosphor-icons/react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { FilterPanel } from "./FilterPanel";
import {
  applyFilters,
  cityOptions,
  DEFAULTS,
  dutchPlaces,
  freshFirst,
  isDefaultView,
  isNew,
  narrowingChips,
  readFilters,
  relaxFilter,
  staleMonths,
  writeFilters,
  type ChipKey,
  type Filters,
  type Posting,
} from "./filters";
import { KM_MONTHLY_EUR, KM_SOURCE, KM_TIER_LABEL } from "./km";
import { euro, formatDay, MatchBadge, PostingRow, type Entrance } from "./PostingRow";
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
const STAGGERED = 8;
const REPO_URL = "https://github.com/optiplex331/SponsorRadar";
const REGISTER_URL =
  "https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants";
const FRESH_COLLECT_MS = 30 * 3_600_000;
const WIDE_QUERY = "(min-width: 47.5rem)"; // the md breakpoint: inline filter panel instead of the sheet
const FILTERS_ID = "filter-panel";

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

const timeFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
});

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json() as Promise<T>;
}

function useWide(): boolean {
  const [wide, setWide] = useState(() => window.matchMedia(WIDE_QUERY).matches);
  useEffect(() => {
    const query = window.matchMedia(WIDE_QUERY);
    const change = () => setWide(query.matches);
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  return wide;
}

/** Rows that animate in: the first load (staggered) and each Show more batch; nothing after a filter change. */
interface EntranceRange {
  from: number;
  to: number;
  kind: Exclude<Entrance, null>;
}

const STATE = "panel px-5 py-6";
const GROUP_H = "mb-2 text-[0.8125rem] font-semibold text-ink-2";
const FOOTER_H = "mb-2 font-serif text-[1.0625rem]/[1.3] font-medium text-ink";
const FOOTER_P = "mb-2.5 max-w-[62ch]";
const LEGEND_ROW = "grid grid-cols-[minmax(0,1fr)] items-baseline gap-1 md:grid-cols-[8.5rem_minmax(0,1fr)] md:gap-3";

export default function App() {
  const [filters, setFilters] = useState<Filters>(() => readFilters(window.location.search));
  const [postings, setPostings] = useState<Posting[] | null>(null);
  const [status, setStatus] = useState<Status | null | undefined>(undefined); // undefined: loading, null: failed
  const [failed, setFailed] = useState(false);
  const [shown, setShown] = useState(PAGE);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [fromPointer, setFromPointer] = useState(false);
  const [entrance, setEntrance] = useState<EntranceRange | null>(null);
  const [lastVisit] = useState(readLastVisit);
  const wide = useWide();
  const filtersButton = useRef<HTMLButtonElement>(null);

  useEffect(() => writeLastVisit(Date.now()), []);

  const load = useCallback(() => {
    setFailed(false);
    setPostings(null);
    setStatus(undefined);
    getJson<Posting[]>("/api/postings").then(
      (data) => {
        setPostings(data);
        setEntrance({ from: 0, to: STAGGERED, kind: "stagger" });
      },
      () => setFailed(true),
    );
    getJson<Status>("/api/status").then(setStatus, () => setStatus(null));
  }, []);

  useEffect(load, [load]);

  const query = writeFilters(filters);
  useEffect(() => {
    window.history.replaceState(null, "", `${window.location.pathname}${query}`);
    setShown(PAGE);
  }, [query]);

  const results = useMemo(() => (postings ? freshFirst(applyFilters(postings, filters)) : []), [postings, filters]);
  const cities = useMemo(() => (postings ? cityOptions(postings) : []), [postings]);
  const known = useMemo(() => (postings ? dutchPlaces(postings) : new Set<string>()), [postings]);
  const update = (patch: Partial<Filters>) => {
    setEntrance(null);
    setFilters((f) => ({ ...f, ...patch }));
  };
  const isDefault = isDefaultView(filters);
  const reset = () => {
    setEntrance(null);
    setFilters({ ...DEFAULTS, km: filters.km });
  };
  const showEmployer = (employer: string, delisted: boolean) => {
    update({ q: employer, ...(delisted ? { sponsor: "all" as const } : {}) });
    window.scrollTo({ top: 0 });
  };
  const toggleFilters = (e: MouseEvent<HTMLButtonElement>) => {
    setFromPointer(e.detail > 0);
    setFiltersOpen((o) => !o);
  };
  const closeFilters = () => {
    setFiltersOpen(false);
    filtersButton.current?.focus();
  };
  const showMore = () => {
    setEntrance({ from: shown, to: shown + PAGE, kind: "plain" });
    setShown((n) => n + PAGE);
  };

  // A returning visitor sees what is new since the last visit first; stale reposts stay with the rest. Grouping runs
  // over all results before paging, so Show more appends to "Earlier" and the "new" count does not change.
  const { ordered, newCount } = useMemo(() => {
    const isFresh = (p: Posting) => isNew(p, lastVisit) && staleMonths(p) === null;
    const fresh = lastVisit === null ? [] : results.filter(isFresh);
    return fresh.length === 0
      ? { ordered: results, newCount: 0 }
      : { ordered: [...fresh, ...results.filter((p) => !isFresh(p))], newCount: fresh.length };
  }, [results, lastVisit]);
  const visible = ordered.slice(0, shown);
  const grouped = newCount > 0;
  const fresh = visible.slice(0, newCount);
  const earlier = visible.slice(fresh.length);
  const entranceOf = (index: number): Entrance =>
    entrance && index >= entrance.from && index < entrance.to ? entrance.kind : null;

  const renderRows = (rows: Posting[], offset: number) => (
    <ol className="panel divide-y divide-line overflow-hidden">
      {rows.map((p, i) => (
        <PostingRow
          key={p.id}
          posting={p}
          km={filters.km}
          isNew={isNew(p, lastVisit) && staleMonths(p) === null}
          known={known}
          heading={grouped ? "h3" : "h2"}
          entrance={entranceOf(offset + i)}
        />
      ))}
    </ol>
  );

  return (
    <>
      <header className="wrap pt-4 pb-3 md:pt-7 md:pb-5">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
          <h1 className="mr-auto flex items-center gap-2.5 font-serif text-2xl/[1.1] font-medium tracking-[-0.015em] md:gap-3 md:text-[2rem]">
            <svg className="size-6 flex-none fill-none stroke-accent stroke-2 md:size-[30px]" viewBox="0 0 32 32" aria-hidden="true">
              <circle cx="16" cy="16" r="13" />
              <circle cx="16" cy="16" r="7.5" />
              <circle className="fill-accent stroke-none" cx="16" cy="16" r="3" />
            </svg>
            NL Sponsor Radar
          </h1>
          <nav aria-label="On this page" className="order-last flex w-full gap-x-5 text-sm md:order-none md:w-auto md:text-[0.9375rem]">
            <a href="#sponsor-lookup" className="inline-flex min-h-8 items-center">
              Check an employer
            </a>
            <a href="#register-changes" className="inline-flex min-h-8 items-center">
              Register changes
            </a>
          </nav>
          <ThemeToggle />
        </div>
        <p className="mt-1.5 mb-2 max-w-[60ch] text-[0.9375rem] text-ink-2 md:mt-2 md:mb-3 md:text-[1.0625rem]">
          Tech jobs in the Netherlands at employers the IND recognises as visa sponsors.
        </p>
        <StatusLine status={status} />
      </header>

      <div>
        <div className="sticky top-0 z-20 border-b border-line bg-bg">
          <form className="wrap flex items-center gap-1.5 py-2 md:gap-3" role="search" onSubmit={(e) => e.preventDefault()}>
            <div className="relative min-w-0 flex-[3]">
              <label htmlFor="q" className="sr-only">
                Role or employer
              </label>
              <MagnifyingGlass
                size={18}
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-2 md:left-3"
              />
              <input
                id="q"
                type="search"
                className="input pr-2 pl-8 md:pr-3 md:pl-9"
                placeholder={wide ? "Role or employer" : "Role, employer"}
                value={filters.q}
                onChange={(e) => update({ q: e.target.value })}
              />
            </div>
            <div className="relative w-20 flex-none md:w-auto md:max-w-60 md:flex-[2]">
              <label htmlFor="city" className="sr-only">
                City
              </label>
              <MapPin
                size={18}
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 left-3 hidden -translate-y-1/2 text-ink-2 md:block"
              />
              <input
                id="city"
                type="search"
                className="input px-2.5 md:pr-3 md:pl-9"
                list="city-options"
                placeholder="City"
                value={filters.city}
                onChange={(e) => update({ city: e.target.value })}
              />
              <datalist id="city-options">
                {cities.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </div>
            <button
              ref={filtersButton}
              type="button"
              className="btn flex-none gap-1.5 px-2.5 aria-expanded:bg-surface-2 md:px-4"
              aria-expanded={filtersOpen}
              aria-controls={FILTERS_ID}
              onClick={toggleFilters}
            >
              <FunnelSimple size={18} aria-hidden="true" />
              Filters
            </button>
          </form>
        </div>

        <div className="wrap">
          {filtersOpen && (
            <FilterPanel
              id={FILTERS_ID}
              filters={filters}
              update={update}
              mode={wide ? "inline" : "sheet"}
              fromPointer={fromPointer}
              count={postings === null ? null : results.length}
              onClose={closeFilters}
            />
          )}

          <ChipRow
            filters={filters}
            isDefault={isDefault}
            onRemove={(key) => update(relaxFilter(filters, key))}
            onReset={reset}
            focusFallback={filtersButton}
            count={
              <p className="ml-auto pl-2 text-sm whitespace-nowrap text-ink-2 tabular-nums" aria-live="polite">
                {postings === null ? (
                  failed ? (
                    "Postings unavailable"
                  ) : (
                    "Loading postings"
                  )
                ) : (
                  <span key={query} className="fade-in">
                    <strong className="font-semibold text-ink">{results.length.toLocaleString("en-GB")}</strong> of{" "}
                    {postings.length.toLocaleString("en-GB")}
                    <span className="sr-only"> postings</span>
                  </span>
                )}
              </p>
            }
          />

          {filters.km && (
            <p className="mb-2 text-[0.8125rem] text-ink-2">
              Salary marks use the 2026 IND threshold, {KM_TIER_LABEL[filters.km].toLowerCase()}:{" "}
              <strong className="text-ink tabular-nums">{euro.format(KM_MONTHLY_EUR[filters.km])}</strong> gross a
              month. <a href={KM_SOURCE}>IND required amounts</a>
            </p>
          )}
        </div>

        <div className="wrap grid grid-cols-[minmax(0,1fr)] items-start gap-8 pt-1 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-7">
          <main className="min-w-0" id="main">
            {failed ? (
              <div className={STATE} role="alert">
                <p className="mb-3 max-w-[60ch]">
                  We couldn't load the postings. The server may be restarting or your connection dropped.
                </p>
                <button type="button" className="btn btn-accent" onClick={load}>
                  Try again
                </button>
              </div>
            ) : postings === null ? (
              <ol className="panel divide-y divide-line" aria-hidden="true">
                {[0, 1, 2, 3].map((i) => (
                  <li key={i} className="grid gap-2.5 px-4 py-4 md:px-5">
                    <span className="bone h-4 w-[55%]" />
                    <span className="bone w-[35%]" />
                    <span className="bone w-[48%]" />
                  </li>
                ))}
              </ol>
            ) : results.length === 0 ? (
              <div className={STATE}>
                <p className="mb-3 max-w-[60ch]">
                  No postings match these filters. Widen the level or experience filter, or clear the search.
                </p>
                {!isDefault && (
                  <button type="button" className="link-button" onClick={reset}>
                    Reset filters
                  </button>
                )}
              </div>
            ) : grouped ? (
              <>
                <h2 className={GROUP_H}>{newCount.toLocaleString("en-GB")} new since your last visit</h2>
                {renderRows(fresh, 0)}
                {earlier.length > 0 && (
                  <>
                    <h2 className={`${GROUP_H} mt-6`}>Earlier</h2>
                    {renderRows(earlier, fresh.length)}
                  </>
                )}
              </>
            ) : (
              renderRows(visible, 0)
            )}

            {results.length > shown && (
              <button type="button" className="btn mt-4 w-full" onClick={showMore}>
                Show {Math.min(PAGE, results.length - shown)} more
              </button>
            )}
          </main>

          <aside className="grid gap-4" aria-label="IND register">
            <SponsorLookup onShowEmployer={showEmployer} />
            <RegisterChanges onShowEmployer={showEmployer} />
          </aside>
        </div>
      </div>

      <Footer />
    </>
  );
}

interface ChipRowProps {
  filters: Filters;
  isDefault: boolean;
  onRemove: (key: ChipKey) => void;
  onReset: () => void;
  focusFallback: RefObject<HTMLButtonElement | null>;
  count: ReactNode;
}

/** Every filter that narrows the list, defaults included; each × widens that one filter. */
function ChipRow({ filters, isDefault, onRemove, onReset, focusFallback, count }: ChipRowProps) {
  const chips = narrowingChips(filters);
  const buttons = useRef(new Map<ChipKey, HTMLButtonElement>());
  const focusAt = useRef<number | null>(null);
  // Chips present at first render do not animate; later additions fade and scale in until their animation ends.
  const seen = useRef<Set<ChipKey> | null>(null);
  const entering = useRef(new Set<ChipKey>());
  const keys = new Set(chips.map((c) => c.key));
  if (seen.current === null) seen.current = keys;
  for (const key of keys) if (!seen.current.has(key)) entering.current.add(key);
  for (const key of entering.current) if (!keys.has(key)) entering.current.delete(key);
  seen.current = keys;

  useEffect(() => {
    if (focusAt.current === null) return;
    const next = chips[focusAt.current] ?? chips[chips.length - 1];
    focusAt.current = null;
    (next ? buttons.current.get(next.key) : focusFallback.current)?.focus();
  });

  return (
    <div className="flex flex-wrap items-center gap-1.5 py-3">
      <ul className="contents" aria-label="Active filters">
        {chips.map((chip, index) => (
          <li
            key={chip.key}
            className={`inline-flex h-8 min-w-0 items-center gap-0.5 rounded-full border border-line-strong bg-surface pr-0.5 pl-3 text-[0.8125rem] text-ink ${
              entering.current.has(chip.key) ? "chip-in" : ""
            }`}
            onAnimationEnd={() => entering.current.delete(chip.key)}
          >
            <span className="max-w-[16rem] truncate">{chip.label}</span>
            <button
              type="button"
              ref={(el) => {
                if (el) buttons.current.set(chip.key, el);
                else buttons.current.delete(chip.key);
              }}
              className="grid size-7 flex-none cursor-pointer place-items-center rounded-full text-ink-2 hover:bg-surface-2 hover:text-ink"
              aria-label={`Remove filter: ${chip.label}`}
              onClick={() => {
                focusAt.current = index;
                onRemove(chip.key);
              }}
            >
              <X size={14} weight="bold" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      {!isDefault && (
        <button type="button" className="link-button min-h-8 px-1.5 text-[0.8125rem]" onClick={onReset}>
          Reset
        </button>
      )}
      {count}
    </div>
  );
}

function StatusLine({ status }: { status: Status | null | undefined }) {
  const cls = "flex flex-wrap gap-x-4 gap-y-0.5 text-[0.8125rem]/normal text-ink-2 tabular-nums";
  if (status === undefined) return <p className={cls}>Loading collection status</p>;
  if (status === null) return <p className={cls}>Collection status unavailable</p>;
  const last = status.last_collect_at ? new Date(status.last_collect_at) : null;
  const fresh = last !== null && Date.now() - last.getTime() < FRESH_COLLECT_MS;
  return (
    <dl className={cls}>
      <div className="flex items-center gap-1.5">
        <dt className="inline-flex items-center gap-[7px]">
          <span className={`size-2 rounded-full ${fresh ? "bg-ok" : "bg-warn"}`} aria-hidden="true" />
          Collected
        </dt>
        <dd className="text-ink">
          {last ? timeFormat.format(last) : "not yet"}
          {last && !fresh && <span className="sr-only"> (more than 30 hours ago)</span>}
        </dd>
      </div>
      <div className="flex gap-1.5">
        <dt>Job boards</dt>
        <dd className="text-ink">
          {status.sources_ok}/{status.sources_total}
        </dd>
      </div>
      <div className="flex gap-1.5">
        <dt>IND register</dt>
        <dd className="text-ink">{status.register_updated_on ? formatDay(status.register_updated_on) : "unknown"}</dd>
      </div>
    </dl>
  );
}

function Footer() {
  return (
    <footer className="wrap mt-14 grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-6 border-t border-line pt-8 pb-[calc(40px+env(safe-area-inset-bottom))] text-sm text-ink-2 min-[56.25rem]:grid-cols-[2fr_1fr_1fr]">
      <section aria-labelledby="about-title">
        <h2 id="about-title" className={FOOTER_H}>
          About and method
        </h2>
        <p className={FOOTER_P}>
          Postings come from public Greenhouse, Ashby, and Recruitee job boards. Employers are linked to the{" "}
          <a href={REGISTER_URL}>IND public register</a> of recognised sponsors. The list is collected once a day,
          around 05:00 UTC, and the register is checked on every run.
        </p>
        <dl className="mb-3 grid gap-2">
          <div className={LEGEND_ROW}>
            <dt>
              <MatchBadge status="kvk_confirmed" />
            </dt>
            <dd>The employer's KvK number was checked by hand against the register.</dd>
          </div>
          <div className={LEGEND_ROW}>
            <dt>
              <MatchBadge status="name_inferred" />
            </dt>
            <dd>The employer's name matches a register organisation. Check the register yourself.</dd>
          </div>
          <div className={LEGEND_ROW}>
            <dt>
              <MatchBadge status="unmatched" />
            </dt>
            <dd>The employer itself is not on the register; a payroll or employer-of-record firm may still hire.</dd>
          </div>
        </dl>
        <p className={FOOTER_P}>Dutch, experience, and sponsorship hints are read from the posting text and can be wrong.</p>
      </section>
      <section aria-labelledby="privacy-title">
        <h2 id="privacy-title" className={FOOTER_H}>
          Privacy
        </h2>
        <p className={FOOTER_P}>
          No cookies and no tracking. Your browser keeps two values in local storage: when you last visited, to mark
          new postings, and your theme choice if you changed it. Neither is sent to us.
        </p>
      </section>
      <section aria-labelledby="disclaimer-title">
        <h2 id="disclaimer-title" className={FOOTER_H}>
          Not advice
        </h2>
        <p className={FOOTER_P}>
          This is not legal or immigration advice. Salary checks use the amounts the job board states. Check the{" "}
          <a href={REGISTER_URL}>IND register</a> and the <a href={KM_SOURCE}>IND required amounts</a> before applying.
        </p>
        <p className={FOOTER_P}>
          <a href={REPO_URL}>Source on GitHub</a>
        </p>
      </section>
    </footer>
  );
}
