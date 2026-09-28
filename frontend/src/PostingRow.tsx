import { ArrowUpRight, Check } from "@phosphor-icons/react";
import { cityLabel, postedAgo, sameEntity, staleMonths, type MatchStatus, type Posting, type Seniority } from "./filters";
import { formatSalary, kmFlag, type KmState, type KmTier } from "./km";

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
const MATCH_CLASS: Record<MatchStatus, string> = {
  kvk_confirmed: "bg-ok-soft text-ok",
  name_inferred: "bg-warn-soft text-warn",
  unmatched: "bg-muted-soft text-muted",
};
const KM_LABEL: Record<KmState, string> = {
  meets: "Meets the threshold",
  crosses: "Threshold: depends on offer",
  below: "Below the threshold",
};
const KM_CLASS: Record<KmState, string> = { meets: "text-ok", crosses: "text-ink", below: "text-warn" };
// "Level not stated" gets no chip: it is the common case and says nothing about the row.
const LEVEL_CHIP: Partial<Record<Seniority, string>> = { intern: "Intern", junior: "Junior", senior: "Senior" };

export const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const dayFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
export const fullDayFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
// `delisted_on` is a calendar day, so it is formatted in UTC; timestamps use the visitor's zone.
const calendarDayFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export function formatDay(iso: string): string {
  const d = new Date(iso);
  return d.getFullYear() === new Date().getFullYear() ? dayFormat.format(d) : fullDayFormat.format(d);
}

export function MatchBadge({ status }: { status: MatchStatus }) {
  return (
    <span className={`badge ${MATCH_CLASS[status]}`} title={MATCH_HINT[status]}>
      {status === "kvk_confirmed" && <Check size={12} weight="bold" aria-hidden="true" />}
      {MATCH_LABEL[status]}
    </span>
  );
}

export type Entrance = "stagger" | "plain" | null;

interface Props {
  posting: Posting;
  km: KmTier | null;
  isNew: boolean;
  known: Set<string>;
  heading: "h2" | "h3";
  entrance: Entrance;
}

export function PostingRow({ posting: p, km, isNew, known, heading: Heading, entrance }: Props) {
  const orgs = p.register_organisations;
  // The register entity only when it is not just the employer with a legal suffix.
  const entity = orgs.find((o) => !sameEntity(p.employer, o));
  const date = p.published_at ?? p.first_seen_at;
  const months = staleMonths(p);
  const salary = formatSalary(p);
  const flag = km ? kmFlag(p, km) : null;
  const place = p.location ? cityLabel(p.location, known) : "";
  const level = LEVEL_CHIP[p.seniority];
  const hasNote = p.delisted_on || p.match_status === "unmatched" || p.sponsorship_stance?.startsWith("refuses");

  return (
    <li
      className={`group px-4 py-3.5 transition-colors duration-150 hover:bg-row-hover md:px-5 ${
        entrance === "stagger" ? "row-in" : entrance === "plain" ? "row-in row-in-plain" : ""
      }`}
      onAnimationEnd={(e) => e.currentTarget.classList.remove("row-in", "row-in-plain")}
    >
      <div className="md:flex md:items-baseline md:justify-between md:gap-6">
        <Heading className="min-w-0 text-[1.0625rem]/snug font-semibold wrap-anywhere">
          <a
            href={p.url}
            target="_blank"
            rel="noopener noreferrer"
            className="-mx-1 rounded-control px-1 py-[11px] text-ink no-underline visited:text-ink-2 hover:underline"
          >
            {p.title}
            <ArrowUpRight
              size={15}
              aria-hidden="true"
              className="ml-1 inline-block align-[-1px] text-ink-2 transition-transform duration-150 ease-out-expo group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
            />
            <span className="sr-only"> (opens the job board in a new tab)</span>
          </a>
        </Heading>
        {(salary || flag) && (
          <div className="mt-0.5 flex-none md:mt-0 md:text-right">
            {salary && <p className="font-semibold tabular-nums md:whitespace-nowrap">{salary}</p>}
            {flag && (
              <p
                className={`text-[0.8125rem] font-semibold ${KM_CLASS[flag.state]}`}
                title={`IND threshold ${euro.format(flag.threshold)} gross a month`}
              >
                {KM_LABEL[flag.state]}
                {flag.checkHolidayAllowance && (
                  <span className="block font-normal text-ink-2">Check: IND excludes the 8% holiday allowance</span>
                )}
              </p>
            )}
          </div>
        )}
      </div>

      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.9375rem]">
        <span className="font-medium">{p.employer}</span>
        <MatchBadge status={p.match_status} />
        {entity && (
          <span className="text-sm text-ink-2 wrap-anywhere" title={orgs.join("\n")}>
            as {entity}
            {orgs.length > 1 && ` +${orgs.length - 1}`}
          </span>
        )}
      </p>

      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
        <ul
          className="flex min-w-0 flex-wrap gap-x-1.5 text-sm text-ink-2 tabular-nums [&>li+li]:before:mr-1.5 [&>li+li]:before:content-['·']"
          aria-label="Details"
        >
          {place && (
            <li className="max-w-full truncate" title={p.location}>
              {place}
            </li>
          )}
          {p.min_years !== null && <li>{p.min_years}+ yrs asked</li>}
          {p.dutch_required && <li className="font-semibold text-ink">Dutch required</li>}
          <li>
            {months === null ? (
              <time dateTime={date}>{formatDay(date)}</time>
            ) : (
              <time dateTime={date} title={fullDayFormat.format(new Date(date))}>
                Posted {postedAgo(months)} ago
              </time>
            )}
          </li>
        </ul>
        {(p.sponsorship_stance === "offers" || level || isNew) && (
          <p className="flex flex-wrap gap-1.5">
            {p.sponsorship_stance === "offers" && (
              <span className="badge badge-plain" title="The posting states visa or relocation support.">
                Visa or relocation support
              </span>
            )}
            {level && <span className="badge badge-plain">{level}</span>}
            {isNew && <span className="badge bg-new text-new-ink">New</span>}
          </p>
        )}
      </div>

      {hasNote && (
        <div className="mt-1.5 grid gap-0.5 text-[0.8125rem] text-ink-2">
          {p.delisted_on ? (
            <p className="text-warn">Removed from register on {calendarDayFormat.format(new Date(p.delisted_on))}</p>
          ) : (
            p.match_status === "unmatched" && (
              <p>
                Employer itself is not on the register; hiring through a payroll or employer-of-record firm may still be
                possible.
              </p>
            )
          )}
          {p.sponsorship_stance === "refuses_relocation" && (
            <p>No relocation support: fine if you already live in the Netherlands.</p>
          )}
          {p.sponsorship_stance === "refuses_visa" && (
            <p className="text-warn">The posting rules out visa sponsorship or asks for existing work rights.</p>
          )}
        </div>
      )}
    </li>
  );
}
