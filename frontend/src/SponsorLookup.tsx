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
    <section className="panel register lookup" id="sponsor-lookup" aria-labelledby="lookup-title">
      <h2 id="lookup-title" className="register-title">
        Is it a sponsor?
      </h2>
      <p className="register-summary">
        Search the latest IND register by organisation name or KvK number, including employers whose job boards we
        do not track.
      </p>
      <form className="lookup-form" role="search" onSubmit={(e) => e.preventDefault()}>
        <div className="field">
          <label htmlFor="sponsor-q">Organisation or KvK number</label>
          <input
            id="sponsor-q"
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
  if (state.kind === "loading") return <p className="register-empty lookup-status">Searching the register</p>;
  if (state.kind === "error") {
    return <p className="register-empty lookup-status">The lookup failed. Try again in a moment.</p>;
  }
  const { query, data } = state;
  if (data.results.length === 0) {
    return (
      <div className="lookup-empty">
        <p>
          No organisation on the register matches <strong>{query}</strong>.
        </p>
        <p>
          The register lists legal entity names, which often differ from the brand: try the name from the company's
          imprint or KvK extract (often ending in B.V.), or its KvK number. If an employer is missing that should be
          there, <a href={ISSUE_URL}>report it on GitHub</a>.
        </p>
      </div>
    );
  }
  return (
    <>
      <ul className="register-list lookup-list">
        {data.results.map((s) => (
          <li key={s.kvk_number}>
            <span className="register-org">{s.organisation}</span>
            <span className="register-kvk">KvK {s.kvk_number}</span>
            {s.brand && <span className="lookup-brand">Known as {s.brand}</span>}
            <span className="lookup-detail">
              {s.first_seen_on &&
                (s.before_history
                  ? `On the register since ${dateFormat.format(new Date(s.first_seen_on))} or earlier`
                  : `Joined the register ${dateFormat.format(new Date(s.first_seen_on))}`)}
            </span>
            <span className="register-links">
              {s.tracked.length === 0 ? (
                <span className="lookup-untracked">We do not track its job board.</span>
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
                    <span key={`${t.kind}:${t.board}`} className="lookup-untracked">
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
        <p className="register-empty lookup-more">Showing the first {data.results.length}. Type more of the name to narrow it.</p>
      )}
    </>
  );
}
