import { useEffect, useState } from "react";

interface RegisterVersion {
  register_updated_on: string | null;
  captured_at: string;
}

interface Tracked {
  employer: string;
  kind: string;
  board: string;
  open_postings: number;
}

interface Added {
  kvk_number: string;
  organisation: string;
  first_seen_on: string | null;
  new_sponsor: boolean;
  tracked: Tracked[];
}

interface Removed {
  kvk_number: string;
  organisation: string;
  tracked: Tracked[];
}

export interface RegisterChangesData {
  current: RegisterVersion | null; // null until the first register snapshot is stored
  previous: RegisterVersion | null;
  added_count: number;
  removed_count: number;
  added: Added[];
  removed: Removed[];
}

// Register dates are calendar days; format them in UTC so they do not shift a day west of Greenwich.
const dateFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const versionDate = (v: RegisterVersion) => dateFormat.format(new Date(v.register_updated_on ?? v.captured_at));
const openPostings = (tracked: Tracked[]) => tracked.reduce((n, t) => n + t.open_postings, 0);

/** Beside the postings on wide screens, below them otherwise; hidden entirely when the endpoint is missing or fails. */
export function RegisterChanges({ onShowEmployer }: { onShowEmployer: (employer: string, delisted: boolean) => void }) {
  const [data, setData] = useState<RegisterChangesData | null>(null);

  useEffect(() => {
    fetch("/api/register-changes")
      .then((r) => (r.ok ? (r.json() as Promise<RegisterChangesData>) : null))
      .then(setData, () => setData(null));
  }, []);

  if (!data || !data.current) return null; // no register snapshot yet: nothing to compare

  const hiring = data.added
    .filter((a) => openPostings(a.tracked) > 0)
    .sort((a, b) => openPostings(b.tracked) - openPostings(a.tracked) || a.organisation.localeCompare(b.organisation));
  const others = data.added.filter((a) => openPostings(a.tracked) === 0);
  const removedHiring = data.removed.filter((r) => openPostings(r.tracked) > 0);

  const employerLink = (t: Tracked, delisted: boolean) => (
    <a
      key={`${t.kind}:${t.board}`}
      href={`?q=${encodeURIComponent(t.employer)}${delisted ? "&sponsor=all" : ""}`}
      onClick={(e) => {
        e.preventDefault();
        onShowEmployer(t.employer, delisted);
      }}
    >
      {t.employer}: {t.open_postings} open {t.open_postings === 1 ? "posting" : "postings"}
    </a>
  );

  return (
    <section className="panel register" id="register-changes" aria-labelledby="register-title">
      <h2 id="register-title" className="register-title">
        Register changes
      </h2>
      {data.previous === null ? (
        <p className="register-summary">
          History starts with this register version ({versionDate(data.current)}). Changes appear after the next IND
          update.
        </p>
      ) : (
        <>
          <p className="register-summary">
            IND register of {versionDate(data.current)} compared with {versionDate(data.previous)}:{" "}
            <strong>{data.added_count.toLocaleString("en-GB")} added</strong>,{" "}
            <strong>{data.removed_count.toLocaleString("en-GB")} removed</strong>.
          </p>

          <h3 className="register-heading">Added sponsors hiring now</h3>
          {hiring.length === 0 ? (
            <p className="register-empty">None of the added sponsors has open postings on a board we track yet.</p>
          ) : (
            <ul className="register-list">
              {hiring.map((a) => (
                <li key={a.kvk_number}>
                  <span className="register-org">{a.organisation}</span>
                  {a.new_sponsor && (
                    <span className="badge badge-plain" title="Joined the register in the last 12 months">
                      New sponsor
                    </span>
                  )}
                  <span className="register-links">{a.tracked.map((t) => employerLink(t, false))}</span>
                </li>
              ))}
            </ul>
          )}

          {others.length > 0 && (
            <details className="register-more">
              <summary>
                {others.length.toLocaleString("en-GB")} other added sponsors, without open postings on boards we track
              </summary>
              <ul className="register-list register-list-plain">
                {others.map((a) => (
                  <li key={a.kvk_number}>
                    <span className="register-org">{a.organisation}</span>
                    <span className="register-kvk">KvK {a.kvk_number}</span>
                    {a.new_sponsor && <span className="badge badge-plain">New sponsor</span>}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {removedHiring.length > 0 && (
            <>
              <h3 className="register-heading">Removed sponsors that still post jobs</h3>
              <ul className="register-list">
                {removedHiring.map((r) => (
                  <li key={r.kvk_number}>
                    <span className="register-org">{r.organisation}</span>
                    <span className="register-links">{r.tracked.map((t) => employerLink(t, true))}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}
