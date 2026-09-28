import { useEffect, useState } from "react";

interface Tracked {
  employer: string;
  kind: string;
  board: string;
  open_postings: number;
}

interface Sponsor {
  kvk_number: string;
  organisation: string;
  brand: string | null;
  first_seen_on: string | null;
  before_history: boolean;
  tracked: Tracked[];
}

interface LookupResponse {
  results: Sponsor[];
  more: boolean;
}

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "done"; query: string; data: LookupResponse };

const ROW = "flex flex-wrap items-center gap-x-2.5 gap-y-1 border-b border-line py-2.5 last:border-b-0";
const MIN_QUERY = 2;
const DEBOUNCE_MS = 300;
const ISSUE_URL = "https://github.com/optiplex331/SponsorRadar/issues/new";
// Register dates are calendar days; format them in UTC so they do not shift a day west of Greenwich.
const dateFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

/** Is an employer on the IND register? The query stays in this component: it is not written to the URL. */
export function SponsorLookup({ onShowEmployer }: { onShowEmployer: (employer: string, delisted: boolean) => void }) {
  const [q, setQ] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  useEffect(() => {
    const query = q.trim();
    if (query.length < MIN_QUERY) {
      setState({ kind: "idle" });
      return;
    }
    setState({ kind: "loading" });
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      fetch(`/api/sponsors?q=${encodeURIComponent(query)}`, { signal: controller.signal })
        .then((r) => {
          if (!r.ok) throw new Error(`lookup returned ${r.status}`);
          return r.json() as Promise<LookupResponse>;
        })
        .then(
          (data) => setState({ kind: "done", query, data }),
          (e: unknown) => {
            if (!(e instanceof DOMException && e.name === "AbortError")) setState({ kind: "error" });
          },
        );
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [q]);

  return (
    <section className="panel scroll-mt-[72px] p-5" id="sponsor-lookup" aria-labelledby="lookup-title">
      <h2 id="lookup-title" className="font-serif text-xl/tight font-medium">
        Is it a sponsor?
      </h2>
      <p className="mt-1.5 text-sm text-ink-2">
        Search the latest IND register by organisation name or KvK number, including employers whose job boards we
        do not track.
      </p>
      <form className="mt-3.5" role="search" onSubmit={(e) => e.preventDefault()}>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="sponsor-q" className="field-label">Organisation or KvK number</label>
          <input
            id="sponsor-q"
            className="input"
            type="search"
            placeholder="Adyen, 34259528"
            autoComplete="off"
            spellCheck={false}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </form>
      <div aria-live="polite">
        <LookupResult state={state} onShowEmployer={onShowEmployer} />
      </div>
    </section>
  );
}

function LookupResult({
  state,
  onShowEmployer,
}: {
  state: State;
  onShowEmployer: (employer: string, delisted: boolean) => void;
}) {
  if (state.kind === "idle") return null;
  if (state.kind === "loading") return <p className="mt-3 text-sm text-ink-2">Searching the register</p>;
  if (state.kind === "error") {
    return <p className="mt-3 text-sm text-ink-2">The lookup failed. Try again in a moment.</p>;
  }
  const { query, data } = state;
  if (data.results.length === 0) {
    return (
      <div className="mt-3 text-sm text-ink-2">
        <p className="mb-1.5">
          No organisation on the register matches <strong className="text-ink wrap-anywhere">{query}</strong>.
        </p>
        <p className="mb-1.5">
          The register lists legal entity names, which often differ from the brand: try the name from the company's
          imprint or KvK extract (often ending in B.V.), or its KvK number. If an employer is missing that should be
          there, <a href={ISSUE_URL}>report it on GitHub</a>.
        </p>
      </div>
    );
  }
  return (
    <>
      <ul className="mt-2">
        {data.results.map((s) => (
          <li key={s.kvk_number} className={ROW}>
            <span className="font-semibold wrap-anywhere">{s.organisation}</span>
            <span className="text-[0.8125rem] text-ink-2 tabular-nums">KvK {s.kvk_number}</span>
            {s.brand && <span className="text-sm text-ink-2">Known as {s.brand}</span>}
            <span className="basis-full text-sm text-ink-2 empty:hidden">
              {s.first_seen_on &&
                (s.before_history
                  ? `On the register since ${dateFormat.format(new Date(s.first_seen_on))} or earlier`
                  : `Joined the register ${dateFormat.format(new Date(s.first_seen_on))}`)}
            </span>
            <span className="flex basis-full flex-wrap gap-x-3.5 gap-y-0.5 text-sm">
              {s.tracked.length === 0 ? (
                <span className="text-ink-2">We do not track its job board.</span>
              ) : (
                s.tracked.map((t) =>
                  t.open_postings > 0 ? (
                    <a
                      key={`${t.kind}:${t.board}`}
                      href={`?q=${encodeURIComponent(t.employer)}`}
                      onClick={(e) => {
                        e.preventDefault();
                        onShowEmployer(t.employer, false);
                      }}
                    >
                      {t.employer}: {t.open_postings} open {t.open_postings === 1 ? "posting" : "postings"}
                    </a>
                  ) : (
                    <span key={`${t.kind}:${t.board}`} className="text-ink-2">
                      {t.employer}: board tracked, no postings in the default view
                    </span>
                  ),
                )
              )}
            </span>
          </li>
        ))}
      </ul>
      {data.more && (
        <p className="mt-3 text-sm text-ink-2">Showing the first {data.results.length}. Type more of the name to narrow it.</p>
      )}
    </>
  );
}
