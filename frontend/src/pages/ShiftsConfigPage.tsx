import { FormEvent, useEffect, useState } from "react";

import { api } from "../api/client";
import { Req } from "../components/Req";
import { ClockIcon, NumField, SectionHead, SwitchRow, TimeField } from "../components/ConfigUi";
import { Icons } from "../components/SidebarIcons";

type YesNo = "Y" | "N";

type Shift = {
  ShiftId: number;
  ShiftName: string;
  ShortName?: string | null;
  StartTime: string;
  EndTime: string;
  GraceInMinutes?: number | null;
  GraceOutMinutes?: number | null;
  Break1Enabled?: YesNo | null;
  Break1StartTime?: string | null;
  Break1EndTime?: string | null;
  Break2Enabled?: YesNo | null;
  Break2StartTime?: string | null;
  Break2EndTime?: string | null;
  IsFlexibleShift?: YesNo | null;
  PunchBeginBeforeMinutes?: number | null;
  PunchEndAfterMinutes?: number | null;
  GraceTimeMinutes?: number | null;
  PartialDayEnabled?: YesNo | null;
  PartialDayWeekday?: string | null;
  PartialDayStartTime?: string | null;
  PartialDayEndTime?: string | null;
  IsDefault?: YesNo | null;
  IsActive?: string | null;
};

type FormState = Omit<Shift, "ShiftId">;

const blankForm: FormState = {
  ShiftName: "",
  ShortName: "",
  StartTime: "09:00",
  EndTime: "18:30",
  GraceInMinutes: 10,
  GraceOutMinutes: 0,
  Break1Enabled: "N",
  Break1StartTime: "13:00",
  Break1EndTime: "13:30",
  Break2Enabled: "N",
  Break2StartTime: "17:00",
  Break2EndTime: "17:15",
  IsFlexibleShift: "N",
  PunchBeginBeforeMinutes: 60,
  PunchEndAfterMinutes: 120,
  GraceTimeMinutes: 10,
  PartialDayEnabled: "N",
  PartialDayWeekday: "Saturday",
  PartialDayStartTime: "00:00",
  PartialDayEndTime: "00:00",
  IsDefault: "N",
  IsActive: "Y",
};

const weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/* ---------- time helpers ---------- */
const toMin = (hhmm?: string | null): number | null => {
  if (!hhmm || !/^\d{1,2}:\d{2}/.test(hhmm)) return null;
  const [h, m] = hhmm.split(":");
  return Number(h) * 60 + Number(m);
};
const fmtDur = (mins: number) => {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h && m ? `${h}h ${m}m` : h ? `${h}h` : `${m}m`;
};
/** Length in minutes; a shift that ends at or before its start runs overnight. */
const spanOf = (start?: string | null, end?: string | null) => {
  const s = toMin(start), e = toMin(end);
  if (s == null || e == null) return null;
  return { mins: e > s ? e - s : e + 1440 - s, overnight: e <= s };
};

/* ---------- 24-hour timeline: shift block plus break markers ---------- */
function Timeline({ start, end, breaks }: { start?: string | null; end?: string | null; breaks: { s?: string | null; e?: string | null }[] }) {
  const s = toMin(start), e = toMin(end);
  const pct = (m: number) => `${(m / 1440) * 100}%`;
  const seg = (from: number, to: number, cls: string, key: string, title?: string) => (
    <span key={key} className={cls} title={title} style={{ left: pct(from), width: pct(Math.max(to - from, 6)) }} />
  );
  const parts: React.ReactNode[] = [];
  if (s != null && e != null) {
    if (e > s) parts.push(seg(s, e, "tl-work", "w"));
    else { parts.push(seg(s, 1440, "tl-work", "w1")); parts.push(seg(0, e, "tl-work", "w2")); }
  }
  breaks.forEach((b, i) => {
    const bs = toMin(b.s), be = toMin(b.e);
    if (bs != null && be != null && be > bs) parts.push(seg(bs, be, "tl-break", "b" + i, `Break ${b.s}–${b.e}`));
  });
  return (
    <div className="tl" role="img" aria-label={s != null && e != null ? `Shift from ${start} to ${end}` : "Shift timeline"}>
      <div className="tl-track">{parts}</div>
      <div className="tl-scale"><span>12 am</span><span>6 am</span><span>12 pm</span><span>6 pm</span><span>12 am</span></div>
    </div>
  );
}

const clock = <ClockIcon />;

export function ShiftsConfigPage() {
  const [rows, setRows] = useState<Shift[]>([]);
  const [form, setForm] = useState<FormState>(blankForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [formError, setFormError] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      const data = await api.getShifts();
      setRows(data);
    } catch (err: any) {
      setRows([]);
      setStatus({ text: err?.message || "Failed to load shifts.", ok: false });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((prev) => ({ ...prev, [key]: value }));
  const on = (v?: string | null) => (v ?? "N") === "Y";

  const openNew = () => { setEditingId(null); setForm(blankForm); setFormError(""); setOpen(true); };

  const openEdit = (row: Shift) => {
    setEditingId(row.ShiftId);
    setForm({
      ShiftName: row.ShiftName,
      ShortName: row.ShortName ?? "",
      StartTime: row.StartTime,
      EndTime: row.EndTime,
      GraceInMinutes: row.GraceInMinutes ?? 10,
      GraceOutMinutes: row.GraceOutMinutes ?? 0,
      Break1Enabled: (row.Break1Enabled as YesNo) ?? "N",
      Break1StartTime: row.Break1StartTime ?? "13:00",
      Break1EndTime: row.Break1EndTime ?? "13:30",
      Break2Enabled: (row.Break2Enabled as YesNo) ?? "N",
      Break2StartTime: row.Break2StartTime ?? "17:00",
      Break2EndTime: row.Break2EndTime ?? "17:15",
      IsFlexibleShift: (row.IsFlexibleShift as YesNo) ?? "N",
      PunchBeginBeforeMinutes: row.PunchBeginBeforeMinutes ?? 60,
      PunchEndAfterMinutes: row.PunchEndAfterMinutes ?? 120,
      GraceTimeMinutes: row.GraceTimeMinutes ?? row.GraceInMinutes ?? 10,
      PartialDayEnabled: (row.PartialDayEnabled as YesNo) ?? "N",
      PartialDayWeekday: row.PartialDayWeekday ?? "Saturday",
      PartialDayStartTime: row.PartialDayStartTime ?? "00:00",
      PartialDayEndTime: row.PartialDayEndTime ?? "00:00",
      IsDefault: (row.IsDefault as YesNo) ?? "N",
      IsActive: row.IsActive ?? "Y",
    });
    setFormError("");
    setOpen(true);
  };

  const close = () => { setOpen(false); setEditingId(null); setFormError(""); };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setFormError("");
    if (!form.ShiftName.trim()) { setFormError("Enter a shift name."); return; }
    if (!form.StartTime || !form.EndTime) { setFormError("Set both the begin and end time."); return; }
    if (on(form.Break1Enabled) && (!form.Break1StartTime || !form.Break1EndTime)) { setFormError("Set the start and end time for Break 1, or switch it off."); return; }
    if (on(form.Break2Enabled) && (!form.Break2StartTime || !form.Break2EndTime)) { setFormError("Set the start and end time for Break 2, or switch it off."); return; }
    setSaving(true);
    try {
      if (editingId === null) await api.createShift(form);
      else await api.updateShift(editingId, form);
      setStatus({ text: editingId === null ? "Shift created." : "Shift updated.", ok: true });
      close();
      await load();
    } catch (err: any) {
      setFormError(err?.message || "Failed to save shift.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (row: Shift) => {
    if (!window.confirm(`Delete the shift "${row.ShiftName}"?`)) return;
    try {
      await api.deleteShift(row.ShiftId);
      setStatus({ text: "Shift deleted.", ok: true });
      await load();
    } catch (err: any) {
      setStatus({ text: err?.message || "Failed to delete shift.", ok: false });
    }
  };

  const span = spanOf(form.StartTime, form.EndTime);

  return (
    <div className="shifts-page">
      <div className="page-head">
        <div>
          <h2>Shifts</h2>
          <p className="sub">Working hours, breaks, punch windows and grace time. Assign shifts to employees from Rosters.</p>
        </div>
        <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ New shift</button>
      </div>

      {status && <p className={status.ok ? "note-ok" : "note-err"} style={{ marginTop: 0 }}>{status.text}</p>}

      {!loading && rows.length === 0 ? (
        <div className="section-card sd-empty">
          <h3>No shifts yet</h3>
          <p>Create your first shift to start calculating late, half-day and overtime.</p>
          <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ New shift</button>
        </div>
      ) : (
        <div className="shift-grid">
          {rows.map((row) => {
            const sp = spanOf(row.StartTime, row.EndTime);
            const breaks = [
              on(row.Break1Enabled) ? { s: row.Break1StartTime, e: row.Break1EndTime } : null,
              on(row.Break2Enabled) ? { s: row.Break2StartTime, e: row.Break2EndTime } : null,
            ].filter(Boolean) as { s?: string | null; e?: string | null }[];
            const inactive = row.IsActive !== "Y";
            return (
              <article key={row.ShiftId} className={"shift-card" + (inactive ? " is-inactive" : "")}>
                <header className="shift-card-head">
                  <div>
                    <h3>{row.ShiftName}{row.ShortName ? <span className="shift-short">{row.ShortName}</span> : null}</h3>
                    <div className="shift-badges">
                      {on(row.IsDefault) && <span className="badge badge-purple">Default</span>}
                      <span className="badge badge-gray">{on(row.IsFlexibleShift) ? "Flexible" : "Fixed"}</span>
                      {inactive && <span className="badge badge-red">Inactive</span>}
                    </div>
                  </div>
                </header>

                <div className="shift-time">
                  <strong>{row.StartTime} – {row.EndTime}</strong>
                  {sp && <span>{fmtDur(sp.mins)}{sp.overnight ? " · overnight" : ""}</span>}
                </div>
                <Timeline start={row.StartTime} end={row.EndTime} breaks={breaks} />

                <dl className="shift-stats">
                  <div><dt>Grace</dt><dd>{row.GraceTimeMinutes ?? row.GraceInMinutes ?? 10} min</dd></div>
                  <div><dt>Punch window</dt><dd>−{row.PunchBeginBeforeMinutes ?? 60} / +{row.PunchEndAfterMinutes ?? 120} min</dd></div>
                  <div><dt>Breaks</dt><dd>{breaks.length ? breaks.map((b) => `${b.s}–${b.e}`).join(", ") : "None"}</dd></div>
                  <div><dt>Partial day</dt><dd>{on(row.PartialDayEnabled) ? `${row.PartialDayWeekday} ${row.PartialDayStartTime}–${row.PartialDayEndTime}` : "None"}</dd></div>
                </dl>

                <footer className="shift-actions">
                  <button type="button" className="btn btn-outline-reports" onClick={() => openEdit(row)}>Edit</button>
                  <button type="button" className="btn btn-outline-reports shift-delete" onClick={() => handleDelete(row)}>Delete</button>
                </footer>
              </article>
            );
          })}
        </div>
      )}

      {open && (
        <div className="modal-overlay" onClick={close}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={editingId === null ? "New shift" : "Edit shift"}>
            <div className="emp-edit-card">
              <div className="emp-edit-head">
                <div className="emp-edit-title">
                  <span className="emp-avatar" aria-hidden>{clock}</span>
                  <div>
                    <h3>{editingId === null ? "New shift" : "Edit shift"}</h3>
                    <span className="emp-edit-sub">{form.ShiftName || "Untitled"}{span ? ` · ${form.StartTime} – ${form.EndTime} · ${fmtDur(span.mins)}` : ""}</span>
                  </div>
                </div>
                <button type="button" className="modal-close" onClick={close} aria-label="Close">×</button>
              </div>

              <div className="emp-edit-scroll">
                <form onSubmit={handleSubmit}>
                  {formError && <div className="emp-error" role="alert">{formError}</div>}

                  <section className="emp-section">
                    <SectionHead icon={Icons.shift} title="Basics" desc="Name and availability" />
                    <div className="emp-grid">
                      <div className="field">
                        <label htmlFor="sh-name">Shift name <Req /></label>
                        <input id="sh-name" value={form.ShiftName} placeholder="e.g. General" onChange={(e) => set("ShiftName", e.target.value)} required />
                      </div>
                      <div className="field">
                        <label htmlFor="sh-short">Short name</label>
                        <input id="sh-short" value={form.ShortName ?? ""} placeholder="e.g. GS" maxLength={10} onChange={(e) => set("ShortName", e.target.value)} />
                      </div>
                      <div className="field">
                        <label>Status</label>
                        <div className="seg" role="group" aria-label="Status">
                          {[["Y", "Active"], ["N", "Inactive"]].map(([v, l]) => (
                            <button key={v} type="button" className={(form.IsActive ?? "Y") === v ? "on" : ""} aria-pressed={(form.IsActive ?? "Y") === v}
                              onClick={() => set("IsActive", v)}>{l}</button>
                          ))}
                        </div>
                      </div>
                    </div>
                  </section>

                  <section className="emp-section">
                    <SectionHead icon={Icons.calendar} title="Working hours" desc="When the shift starts and ends" />
                    <div className="hours-row">
                      <div>
                        <label className="field-label" htmlFor="sh-start">Begin <Req /></label>
                        <TimeField id="sh-start" label="Begin time" value={form.StartTime} onChange={(v) => set("StartTime", v)} />
                      </div>
                      <span className="meal-to">to</span>
                      <div>
                        <label className="field-label" htmlFor="sh-end">End <Req /></label>
                        <TimeField id="sh-end" label="End time" value={form.EndTime} onChange={(v) => set("EndTime", v)} />
                      </div>
                      {span && <span className="hours-total">{fmtDur(span.mins)}{span.overnight ? " · overnight" : ""}</span>}
                    </div>
                    <Timeline start={form.StartTime} end={form.EndTime}
                      breaks={[
                        on(form.Break1Enabled) ? { s: form.Break1StartTime, e: form.Break1EndTime } : {},
                        on(form.Break2Enabled) ? { s: form.Break2StartTime, e: form.Break2EndTime } : {},
                      ]} />
                    <div className="switch-list">
                      <SwitchRow id="sh-flex" checked={on(form.IsFlexibleShift)} onChange={(v) => set("IsFlexibleShift", v ? "Y" : "N")}
                        title="Flexible shift" desc="No fixed start time. Attendance counts total hours worked." />
                      <SwitchRow id="sh-default" checked={on(form.IsDefault)} onChange={(v) => set("IsDefault", v ? "Y" : "N")}
                        title="Default shift" desc="Used for anyone with no roster on that date. Only one shift can be the default." />
                    </div>
                  </section>

                  <section className="emp-section">
                    <SectionHead icon={Icons.holiday} title="Breaks" desc="Unpaid time inside the shift" />
                    <div className="break-list">
                      {([1, 2] as const).map((n) => {
                        const enabled = on(form[`Break${n}Enabled` as const]);
                        return (
                          <div key={n} className={"break-row" + (enabled ? "" : " is-off")}>
                            <SwitchRow id={`sh-b${n}`} checked={enabled} onChange={(v) => set(`Break${n}Enabled` as const, v ? "Y" : "N")} title={`Break ${n}`} />
                            <TimeField id={`sh-b${n}s`} label={`Break ${n} start`} disabled={!enabled}
                              value={(form[`Break${n}StartTime` as const] as string) ?? ""} onChange={(v) => set(`Break${n}StartTime` as const, v)} />
                            <span className="meal-to">to</span>
                            <TimeField id={`sh-b${n}e`} label={`Break ${n} end`} disabled={!enabled}
                              value={(form[`Break${n}EndTime` as const] as string) ?? ""} onChange={(v) => set(`Break${n}EndTime` as const, v)} />
                          </div>
                        );
                      })}
                    </div>
                  </section>

                  <section className="emp-section">
                    <SectionHead icon={Icons.commands} title="Punch and grace rules" desc="How punches around the shift are treated" />
                    <div className="rule-grid">
                      <div>
                        <label className="field-label" htmlFor="sh-pb">Punch begins before</label>
                        <NumField id="sh-pb" max={1440} value={form.PunchBeginBeforeMinutes ?? 60} onChange={(v) => set("PunchBeginBeforeMinutes", v)} />
                        <span className="field-hint">Earliest punch counted as this shift's start.</span>
                      </div>
                      <div>
                        <label className="field-label" htmlFor="sh-pe">Punch ends after</label>
                        <NumField id="sh-pe" max={1440} value={form.PunchEndAfterMinutes ?? 120} onChange={(v) => set("PunchEndAfterMinutes", v)} />
                        <span className="field-hint">Latest punch counted as this shift's end.</span>
                      </div>
                      <div>
                        <label className="field-label" htmlFor="sh-gr">Grace time</label>
                        <NumField id="sh-gr" max={240} value={form.GraceTimeMinutes ?? 10}
                          onChange={(v) => { set("GraceTimeMinutes", v); set("GraceInMinutes", v); }} />
                        <span className="field-hint">Minutes after the start before someone is late.</span>
                      </div>
                    </div>
                  </section>

                  <section className="emp-section">
                    <SectionHead icon={Icons.leaves} title="Partial day" desc="A shorter day, such as a half-working Saturday" />
                    <SwitchRow id="sh-partial" checked={on(form.PartialDayEnabled)} onChange={(v) => set("PartialDayEnabled", v ? "Y" : "N")}
                      title="Use a different timing on one weekday" />
                    <div className={"hours-row" + (on(form.PartialDayEnabled) ? "" : " is-off")} style={{ marginTop: 16 }}>
                      <div>
                        <label className="field-label" htmlFor="sh-pd">Weekday</label>
                        <select id="sh-pd" value={form.PartialDayWeekday ?? "Saturday"} disabled={!on(form.PartialDayEnabled)}
                          onChange={(e) => set("PartialDayWeekday", e.target.value)}>
                          {weekdays.map((d) => <option key={d} value={d}>{d}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="field-label" htmlFor="sh-pds">From</label>
                        <TimeField id="sh-pds" label="Partial day start" disabled={!on(form.PartialDayEnabled)}
                          value={form.PartialDayStartTime ?? ""} onChange={(v) => set("PartialDayStartTime", v)} />
                      </div>
                      <span className="meal-to">to</span>
                      <div>
                        <label className="field-label" htmlFor="sh-pde">To</label>
                        <TimeField id="sh-pde" label="Partial day end" disabled={!on(form.PartialDayEnabled)}
                          value={form.PartialDayEndTime ?? ""} onChange={(v) => set("PartialDayEndTime", v)} />
                      </div>
                    </div>
                  </section>

                  <div className="emp-edit-actions">
                    <button type="button" className="btn btn-outline-reports" onClick={close}>Cancel</button>
                    <button type="submit" className="btn btn-primary-purple" disabled={saving}>
                      {saving ? "Saving…" : editingId === null ? "Create shift" : "Save changes"}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
