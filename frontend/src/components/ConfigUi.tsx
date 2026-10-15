import { FormEvent, ReactNode, useEffect } from "react";

/** Shared building blocks for the Configuration pages (Shifts, Rosters, Holidays, Leave Types, Categories). */

export const ClockIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="9" /><polyline points="12 7 12 12 15 14" />
  </svg>
);

export function TimeField({ id, value, onChange, disabled, label }: { id: string; value: string; onChange: (v: string) => void; disabled?: boolean; label: string }) {
  return (
    <div className={"time-field" + (disabled ? " is-disabled" : "")}>
      <ClockIcon />
      <input id={id} type="time" value={value} disabled={disabled} aria-label={label} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

export function NumField({ id, value, onChange, max, suffix = "min", disabled }: { id: string; value: number; onChange: (v: number) => void; max: number; suffix?: string; disabled?: boolean }) {
  return (
    <div className={"num-field" + (disabled ? " is-disabled" : "")}>
      <input id={id} type="number" inputMode="numeric" min={0} max={max} value={value} disabled={disabled}
        onChange={(e) => onChange(Math.min(max, Math.max(0, Number(e.target.value || 0))))} />
      <span>{suffix}</span>
    </div>
  );
}

export function SwitchRow({ checked, onChange, title, desc, id, disabled }: { checked: boolean; onChange: (v: boolean) => void; title: string; desc?: string; id: string; disabled?: boolean }) {
  return (
    <label className="switch-row" htmlFor={id}>
      <input id={id} type="checkbox" className="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span><strong>{title}</strong>{desc && <small>{desc}</small>}</span>
    </label>
  );
}

export function SectionHead({ icon, title, desc }: { icon: ReactNode; title: string; desc: string }) {
  return (
    <div className="emp-sech">
      <span className="emp-tile" aria-hidden>{icon}</span>
      <div><h4>{title}</h4><p>{desc}</p></div>
    </div>
  );
}

/** Segmented control for a small fixed set of choices. */
export function Segmented({ value, options, onChange, label }: { value: string; options: [string, string][]; onChange: (v: string) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, l]) => (
        <button key={v} type="button" className={value === v ? "on" : ""} aria-pressed={value === v} onClick={() => onChange(v)}>{l}</button>
      ))}
    </div>
  );
}

/** Popup used by every Configuration editor: header, scrolling sections, sticky footer. */
export function ConfigModal({
  title, subtitle, icon, onClose, onSubmit, error, saving, submitLabel, children,
}: {
  title: string;
  subtitle?: string;
  icon: ReactNode;
  onClose: () => void;
  onSubmit: (e: FormEvent) => void;
  error?: string;
  saving?: boolean;
  submitLabel: string;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
        <div className="emp-edit-card">
          <div className="emp-edit-head">
            <div className="emp-edit-title">
              <span className="emp-avatar" aria-hidden>{icon}</span>
              <div>
                <h3>{title}</h3>
                {subtitle && <span className="emp-edit-sub">{subtitle}</span>}
              </div>
            </div>
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close">×</button>
          </div>
          <div className="emp-edit-scroll">
            <form onSubmit={onSubmit}>
              {error && <div className="emp-error" role="alert">{error}</div>}
              {children}
              <div className="emp-edit-actions">
                <button type="button" className="btn btn-outline-reports" onClick={onClose}>Cancel</button>
                <button type="submit" className="btn btn-primary-purple" disabled={saving}>{saving ? "Saving…" : submitLabel}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export const fmtDate = (iso?: string | null, withYear = true) => {
  if (!iso) return "";
  const d = new Date(iso.slice(0, 10) + "T00:00:00");
  return d.toLocaleDateString(undefined, withYear ? { day: "numeric", month: "short", year: "numeric" } : { day: "numeric", month: "short" });
};

/** Success/error note under a page header. */
export function Flash({ status }: { status: { text: string; ok: boolean } | null }) {
  return status ? <p className={status.ok ? "note-ok" : "note-err"} style={{ marginTop: 0 }} role="status">{status.text}</p> : null;
}
