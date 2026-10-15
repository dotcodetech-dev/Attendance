import { FormEvent, useEffect, useState } from "react";

import { api } from "../api/client";
import { ConfigModal, Flash, NumField, SectionHead, Segmented, SwitchRow } from "../components/ConfigUi";
import { Req } from "../components/Req";
import { Icons } from "../components/SidebarIcons";

type YesNo = "Y" | "N";

const OT_FORMULAS = [
  "Total Duration - Shift Hours",
  "In Out Punch - Shift End Time",
  "Early Coming + Late Going",
  "OT Not Applicable",
];

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export type Category = {
  CategoryId: number;
  CategoryName: string;
  ShortName?: string | null;
  OTFormula?: string | null;
  MinOTMinutes?: number | null;
  MaxOTMinutes?: number | null;
  GraceLateComingMinutes?: number | null;
  GraceEarlyGoingMinutes?: number | null;
  WeeklyOff1Enabled?: YesNo | null;
  WeeklyOff1Weekday?: string | null;
  WeeklyOff2Enabled?: YesNo | null;
  WeeklyOff2Weekday?: string | null;
  WeeklyOff2Occurrence1?: YesNo | null;
  WeeklyOff2Occurrence2?: YesNo | null;
  WeeklyOff2Occurrence3?: YesNo | null;
  WeeklyOff2Occurrence4?: YesNo | null;
  WeeklyOff2Occurrence5?: YesNo | null;
  ConsiderEarlyComingPunch?: YesNo | null;
  ConsiderOnlyFirstLastPunch?: YesNo | null;
  ConsiderLateGoingPunch?: YesNo | null;
  DeductBreakHours?: YesNo | null;
  NeglectLastInPunch?: YesNo | null;
  HalfDayIfWorkDurationLessThanMinutes?: number | null;
  AbsentIfWorkDurationLessThanMinutes?: number | null;
  PartialDayCalculateHalfDayIfWorkDurationLessThanMinutes?: number | null;
  PartialDayCalculateAbsentIfWorkDurationLessThanMinutes?: number | null;
  MarkWeeklyOffHolidayAsAbsentPrefixAbsent?: YesNo | null;
  MarkWeeklyOffHolidayAsAbsentSuffixAbsent?: YesNo | null;
  MarkWeeklyOffHolidayAsAbsentBothSidesAbsent?: YesNo | null;
  MarkHalfDayWhenLateForDays?: number | null;
  MarkHalfDayIfLateByMinutes?: number | null;
  MarkHalfDayIfEarlyGoingByMinutes?: number | null;
  IsActive?: YesNo | null;
};

type FormState = Omit<Category, "CategoryId">;

const defaultCategoryForm: FormState = {
  CategoryName: "",
  ShortName: "",
  OTFormula: "Total Duration - Shift Hours",
  MinOTMinutes: 30,
  MaxOTMinutes: 0,
  GraceLateComingMinutes: 15,
  GraceEarlyGoingMinutes: 15,
  WeeklyOff1Enabled: "N",
  WeeklyOff1Weekday: "Sunday",
  WeeklyOff2Enabled: "N",
  WeeklyOff2Weekday: "Saturday",
  WeeklyOff2Occurrence1: "Y",
  WeeklyOff2Occurrence2: "Y",
  WeeklyOff2Occurrence3: "N",
  WeeklyOff2Occurrence4: "Y",
  WeeklyOff2Occurrence5: "N",
  ConsiderEarlyComingPunch: "N",
  ConsiderOnlyFirstLastPunch: "Y",
  ConsiderLateGoingPunch: "Y",
  DeductBreakHours: "N",
  NeglectLastInPunch: "N",
  HalfDayIfWorkDurationLessThanMinutes: 240,
  AbsentIfWorkDurationLessThanMinutes: 120,
  PartialDayCalculateHalfDayIfWorkDurationLessThanMinutes: 0,
  PartialDayCalculateAbsentIfWorkDurationLessThanMinutes: 0,
  MarkWeeklyOffHolidayAsAbsentPrefixAbsent: "N",
  MarkWeeklyOffHolidayAsAbsentSuffixAbsent: "N",
  MarkWeeklyOffHolidayAsAbsentBothSidesAbsent: "N",
  MarkHalfDayWhenLateForDays: 0,
  MarkHalfDayIfLateByMinutes: 0,
  MarkHalfDayIfEarlyGoingByMinutes: 0,
  IsActive: "Y",
};

const on = (v?: string | null, fallback: YesNo = "N") => (v ?? fallback) === "Y";
const mins = (n?: number | null) => `${n ?? 0} min`;

const PUNCH_RULES: { key: keyof FormState; fallback: YesNo; title: string; desc: string }[] = [
  { key: "ConsiderOnlyFirstLastPunch", fallback: "Y", title: "Use only the first and last punch", desc: "Ignore the punches in between when working out hours." },
  { key: "ConsiderEarlyComingPunch", fallback: "N", title: "Count early coming", desc: "Time before the shift starts counts as worked time." },
  { key: "ConsiderLateGoingPunch", fallback: "Y", title: "Count late going", desc: "Time after the shift ends counts as worked time." },
  { key: "DeductBreakHours", fallback: "N", title: "Deduct break hours", desc: "Remove the shift's break time from worked hours." },
  { key: "NeglectLastInPunch", fallback: "N", title: "Ignore the last IN punch", desc: "If the last punch is an IN with no OUT, leave it out." },
];

export function CategoriesConfigPage() {
  const [rows, setRows] = useState<Category[]>([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState<FormState>(defaultCategoryForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      setRows(await api.getCategories());
    } catch (err: any) {
      setRows([]);
      setStatus({ text: err?.message || "Failed to load categories.", ok: false });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((p) => ({ ...p, [key]: value }));

  const openNew = () => { setEditingId(null); setForm(defaultCategoryForm); setFormError(""); setOpen(true); };
  const openEdit = (row: Category) => {
    const { CategoryId, ...rest } = row;
    setEditingId(CategoryId);
    setForm({ ...defaultCategoryForm, ...rest });
    setFormError("");
    setOpen(true);
  };
  const close = () => { setOpen(false); setEditingId(null); setFormError(""); };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError("");
    if (!form.CategoryName.trim()) { setFormError("Enter a category name."); return; }
    setSaving(true);
    try {
      const payload = { ...form, CategoryName: form.CategoryName.trim() };
      if (editingId === null) await api.createCategory(payload);
      else await api.updateCategory(editingId, payload);
      setStatus({ text: editingId === null ? "Category created." : "Category updated.", ok: true });
      close();
      await load();
    } catch (err: any) {
      setFormError(err?.message || "Failed to save category.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (row: Category) => {
    if (!window.confirm(`Delete the category "${row.CategoryName}"? Employees using it will need a new category.`)) return;
    try {
      await api.deleteCategory(row.CategoryId);
      setStatus({ text: "Category deleted.", ok: true });
      await load();
    } catch (err: any) {
      setStatus({ text: err?.message || "Failed to delete.", ok: false });
    }
  };

  const offDays = (r: Category) =>
    [on(r.WeeklyOff1Enabled) ? r.WeeklyOff1Weekday : null, on(r.WeeklyOff2Enabled) ? r.WeeklyOff2Weekday : null].filter(Boolean).join(", ") || "None";

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Attendance Categories</h2>
          <p className="sub">Rules that turn punches into attendance: overtime, grace times, weekly offs and half-day or absent limits. Each employee belongs to one category.</p>
        </div>
        <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ New category</button>
      </div>

      <Flash status={status} />

      {!loading && rows.length === 0 ? (
        <div className="section-card cfg-empty">
          <strong>No categories yet</strong>
          <span>Add a category, then assign it to employees to drive their attendance rules.</span>
          <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ New category</button>
        </div>
      ) : (
        <div className="shift-grid">
          {rows.map((row) => {
            const inactive = row.IsActive !== "Y";
            return (
              <article key={row.CategoryId} className={"shift-card" + (inactive ? " is-inactive" : "")}>
                <header className="shift-card-head">
                  <h3>{row.CategoryName}{row.ShortName ? <span className="shift-short">{row.ShortName}</span> : null}</h3>
                  <div className="shift-badges">
                    <span className="badge badge-purple">{row.OTFormula || "No OT rule"}</span>
                    {inactive && <span className="badge badge-red">Inactive</span>}
                  </div>
                </header>
                <dl className="shift-stats" style={{ borderTop: 0, paddingTop: 0 }}>
                  <div><dt>Grace late / early</dt><dd>{mins(row.GraceLateComingMinutes)} / {mins(row.GraceEarlyGoingMinutes)}</dd></div>
                  <div><dt>Weekly off</dt><dd>{offDays(row)}</dd></div>
                  <div><dt>Half day if under</dt><dd>{mins(row.HalfDayIfWorkDurationLessThanMinutes)}</dd></div>
                  <div><dt>Absent if under</dt><dd>{mins(row.AbsentIfWorkDurationLessThanMinutes)}</dd></div>
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
        <ConfigModal
          title={editingId === null ? "New category" : "Edit category"}
          subtitle={form.CategoryName || "Attendance and overtime rules"}
          icon={Icons.tag}
          onClose={close} onSubmit={handleSubmit} error={formError} saving={saving}
          submitLabel={editingId === null ? "Create category" : "Save changes"}
        >
          <section className="emp-section">
            <SectionHead icon={Icons.tag} title="Basics" desc="Name and availability" />
            <div className="emp-grid">
              <div className="field">
                <label htmlFor="ct-name">Category name <Req /></label>
                <input id="ct-name" value={form.CategoryName} placeholder="e.g. General" onChange={(e) => set("CategoryName", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="ct-short">Short name</label>
                <input id="ct-short" value={form.ShortName ?? ""} placeholder="e.g. GEN" maxLength={10} onChange={(e) => set("ShortName", e.target.value)} />
              </div>
              <div className="field">
                <label>Status</label>
                <Segmented label="Status" value={form.IsActive ?? "Y"} onChange={(v) => set("IsActive", v as YesNo)} options={[["Y", "Active"], ["N", "Inactive"]]} />
              </div>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.logs} title="Overtime" desc="How extra hours are calculated" />
            <div className="emp-grid">
              <div className="field field-span-2">
                <label htmlFor="ct-ot">OT formula</label>
                <select id="ct-ot" value={form.OTFormula ?? ""} onChange={(e) => set("OTFormula", e.target.value)}>
                  {OT_FORMULAS.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
            </div>
            <div className="rule-grid" style={{ marginTop: 20 }}>
              <div>
                <label className="field-label" htmlFor="ct-minot">Minimum OT</label>
                <NumField id="ct-minot" max={1440} value={form.MinOTMinutes ?? 30} onChange={(v) => set("MinOTMinutes", v)} />
                <span className="field-hint">Less than this is ignored.</span>
              </div>
              <div>
                <label className="field-label" htmlFor="ct-maxot">Maximum OT</label>
                <NumField id="ct-maxot" max={1440} value={form.MaxOTMinutes ?? 0} onChange={(v) => set("MaxOTMinutes", v)} />
                <span className="field-hint">0 means no cap.</span>
              </div>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.commands} title="Grace" desc="Minutes allowed before it counts as late or early" />
            <div className="rule-grid">
              <div>
                <label className="field-label" htmlFor="ct-gl">Late coming</label>
                <NumField id="ct-gl" max={240} value={form.GraceLateComingMinutes ?? 15} onChange={(v) => set("GraceLateComingMinutes", v)} />
              </div>
              <div>
                <label className="field-label" htmlFor="ct-ge">Early going</label>
                <NumField id="ct-ge" max={240} value={form.GraceEarlyGoingMinutes ?? 15} onChange={(v) => set("GraceEarlyGoingMinutes", v)} />
              </div>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.holiday} title="Weekly off" desc="Days that are not working days" />
            <div className="break-list">
              {([1, 2] as const).map((n) => {
                const enabled = on(form[`WeeklyOff${n}Enabled` as const]);
                return (
                  <div key={n} className={"break-row" + (enabled ? "" : " is-off")}>
                    <SwitchRow id={`ct-wo${n}`} checked={enabled} onChange={(v) => set(`WeeklyOff${n}Enabled` as const, (v ? "Y" : "N") as YesNo)} title={`Weekly off ${n}`} />
                    <select aria-label={`Weekly off ${n} weekday`} disabled={!enabled} value={(form[`WeeklyOff${n}Weekday` as const] as string) ?? ""}
                      onChange={(e) => set(`WeeklyOff${n}Weekday` as const, e.target.value)} style={{ width: 200 }}>
                      {WEEKDAYS.map((d) => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.enrollment} title="Punch rules" desc="Which punches count towards worked hours" />
            <div className="switch-list" style={{ marginTop: 0, paddingTop: 0, borderTop: 0 }}>
              {PUNCH_RULES.map((r) => (
                <SwitchRow key={r.key} id={`ct-${r.key}`} checked={on(form[r.key] as string | null | undefined, r.fallback)}
                  onChange={(v) => set(r.key, (v ? "Y" : "N") as never)} title={r.title} desc={r.desc} />
              ))}
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.leaves} title="Half-day and absent limits" desc="When short hours change the day's status" />
            <div className="rule-grid">
              <div>
                <label className="field-label" htmlFor="ct-hd">Half day if worked under</label>
                <NumField id="ct-hd" max={1440} value={form.HalfDayIfWorkDurationLessThanMinutes ?? 240} onChange={(v) => set("HalfDayIfWorkDurationLessThanMinutes", v)} />
              </div>
              <div>
                <label className="field-label" htmlFor="ct-ab">Absent if worked under</label>
                <NumField id="ct-ab" max={1440} value={form.AbsentIfWorkDurationLessThanMinutes ?? 120} onChange={(v) => set("AbsentIfWorkDurationLessThanMinutes", v)} />
              </div>
              <div />
              <div>
                <label className="field-label" htmlFor="ct-hl">Half day if late by</label>
                <NumField id="ct-hl" max={1440} value={form.MarkHalfDayIfLateByMinutes ?? 0} onChange={(v) => set("MarkHalfDayIfLateByMinutes", v)} />
                <span className="field-hint">0 turns this rule off.</span>
              </div>
              <div>
                <label className="field-label" htmlFor="ct-he">Half day if leaving early by</label>
                <NumField id="ct-he" max={1440} value={form.MarkHalfDayIfEarlyGoingByMinutes ?? 0} onChange={(v) => set("MarkHalfDayIfEarlyGoingByMinutes", v)} />
                <span className="field-hint">0 turns this rule off.</span>
              </div>
            </div>
          </section>
        </ConfigModal>
      )}
    </div>
  );
}
