import { X } from "@phosphor-icons/react";
import { useEffect, useRef, type KeyboardEvent } from "react";
import { SENIORITIES, type Filters, type Seniority } from "./filters";
import { KM_MONTHLY_EUR, KM_SOURCE, KM_TIER_LABEL, KM_TIERS, type KmTier } from "./km";
import { euro } from "./PostingRow";

const SENIORITY_LABEL: Record<Seniority, string> = {
  intern: "Intern",
  junior: "Junior",
  unspecified: "Level not stated",
  senior: "Senior",
};
const FIELD = "m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0";
const TOGGLE = "flex cursor-pointer items-start gap-2.5 py-2 text-[0.9375rem]";
const TOGGLE_INPUT = "mt-[3px] size-[18px] flex-none accent-accent";

interface Props {
  id: string;
  filters: Filters;
  update: (patch: Partial<Filters>) => void;
  /** "inline" under the toolbar from 760px; "sheet" is a modal bottom sheet on narrower screens. */
  mode: "inline" | "sheet";
  /** The sheet slides up only when a pointer opened it; keyboard opens fade. */
  fromPointer: boolean;
  count: number | null;
  onClose: () => void;
}

/** The secondary filters. They apply live; closing only hides them. */
export function FilterPanel({ id, filters, update, mode, fromPointer, count, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialog.current;
    if (mode !== "sheet" || !el) return;
    // No cleanup: closing here would fire "close" and shut the panel under StrictMode's effect replay.
    // Unmounting removes the dialog, which ends the modal state without a close event.
    if (!el.open) el.showModal();
  }, [mode]);

  const toggleSeniority = (s: Seniority) =>
    update({
      seniority: filters.seniority.includes(s)
        ? filters.seniority.filter((x) => x !== s)
        : SENIORITIES.filter((x) => x === s || filters.seniority.includes(x)),
    });

  const form = (
    <form
      className="grid grid-cols-2 items-start gap-x-3 gap-y-4 md:grid-cols-4 md:gap-x-4"
      onSubmit={(e) => e.preventDefault()}
      aria-label="More filters"
    >
      <div className={FIELD}>
        <label htmlFor="years" className="field-label">
          Experience asked
        </label>
        <select
          id="years"
          className="input"
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
      <div className={FIELD}>
        <label htmlFor="sponsor" className="field-label">
          Employers
        </label>
        <select
          id="sponsor"
          className="input"
          value={filters.sponsor}
          onChange={(e) => update({ sponsor: e.target.value as Filters["sponsor"] })}
        >
          <option value="matched">On IND register</option>
          <option value="all">All employers</option>
        </select>
      </div>
      <fieldset className={`${FIELD} col-span-full md:col-span-2`}>
        <legend className="field-label mb-1.5">Level</legend>
        <div className="flex flex-wrap gap-1.5">
          {SENIORITIES.map((s) => (
            <label key={s} className="check-chip">
              <input type="checkbox" checked={filters.seniority.includes(s)} onChange={() => toggleSeniority(s)} />
              <span>{SENIORITY_LABEL[s]}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className={`${FIELD} col-span-full md:col-span-2`}>
        <label htmlFor="km" className="field-label">
          Salary vs. visa threshold
        </label>
        <select
          id="km"
          className="input"
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
        {filters.km && (
          <p className="text-[0.8125rem] text-ink-2">
            Salary compared with the IND highly skilled migrant threshold for 2026,{" "}
            {KM_TIER_LABEL[filters.km].toLowerCase()}:{" "}
            <strong className="text-ink tabular-nums">{euro.format(KM_MONTHLY_EUR[filters.km])}</strong> gross a
            month, without holiday allowance. Only postings with a salary in euros per month or year get a mark;
            yearly figures are divided by 12. <a href={KM_SOURCE}>IND required amounts</a>.
          </p>
        )}
      </div>
      <div className="col-span-full flex flex-col md:col-span-2 md:pt-6">
        <label className={TOGGLE}>
          <input
            type="checkbox"
            className={TOGGLE_INPUT}
            checked={filters.hideDutch}
            onChange={(e) => update({ hideDutch: e.target.checked })}
          />
          <span>Hide jobs that require Dutch</span>
        </label>
        <label className={TOGGLE}>
          <input
            type="checkbox"
            className={TOGGLE_INPUT}
            checked={!filters.showRefusesVisa}
            onChange={(e) => update({ showRefusesVisa: !e.target.checked })}
          />
          <span>Hide jobs that rule out visa sponsorship or need existing work rights</span>
        </label>
      </div>
    </form>
  );

  if (mode === "inline") {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    return (
      <div
        id={id}
        className="panel mt-3 p-4 transition-opacity duration-150 starting:opacity-0 md:p-5"
        onKeyDown={onKeyDown}
      >
        {form}
      </div>
    );
  }

  return (
    <dialog
      ref={dialog}
      id={id}
      aria-labelledby={`${id}-title`}
      className={`sheet ${fromPointer ? "sheet-slide" : ""}`}
      onClose={onClose}
      onClick={(e) => {
        // A click on the backdrop lands on the dialog element itself.
        if (e.target === e.currentTarget) e.currentTarget.close();
      }}
    >
      <div className="flex items-center justify-between gap-4 border-b border-line px-4 py-2">
        <h2 id={`${id}-title`} className="font-serif text-xl/tight font-medium">
          Filters
        </h2>
        <button
          type="button"
          className="btn -mr-2 w-11 border-transparent p-0"
          aria-label="Close filters"
          onClick={() => dialog.current?.close()}
        >
          <X size={20} aria-hidden="true" />
        </button>
      </div>
      <div className="px-4 py-4">{form}</div>
      <div className="sticky bottom-0 border-t border-line bg-surface px-4 pt-3 pb-[max(12px,env(safe-area-inset-bottom))]">
        <button type="button" className="btn btn-accent w-full min-h-11" onClick={() => dialog.current?.close()}>
          {count === null ? "Show postings" : `Show ${count.toLocaleString("en-GB")} ${count === 1 ? "posting" : "postings"}`}
        </button>
      </div>
    </dialog>
  );
}
