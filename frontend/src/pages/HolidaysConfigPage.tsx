import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import { ConfigModal, Flash, SectionHead, Segmented } from "../components/ConfigUi";
import { Req } from "../components/Req";
import { Icons } from "../components/SidebarIcons";

type Holiday = {
  HolidayId: number;
  HolidayDate: string;
  HolidayName: string;
  Category: string;
  IsActive?: string | null;
};

const CATEGORIES: { value: string; label: string; badge: string; help: string }[] = [
  { value: "Public", label: "Public holiday", badge: "badge-purple", help: "National or state holiday" },
  { value: "Company", label: "Company holiday", badge: "badge-amber", help: "Declared by the organisation" },
  { value: "WeeklyOff", label: "Weekly off", badge: "badge-blue", help: "A recurring day off, entered by date" },
];
const catOf = (v: string) => CATEGORIES.find((c) => c.value === v) ?? { value: v, label: v, badge: "badge-gray", help: "" };

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

type FormState = Omit<Holiday, "HolidayId">;
const blankForm = (year: number): FormState => {
  const t = todayIso();
  return { HolidayDate: t.startsWith(String(year)) ? t : `${year}-01-01`, HolidayName: "", Category: "Public", IsActive: "Y" };
};

const monthName = (iso: string) => new Date(iso.slice(0, 10) + "T00:00:00").toLocaleDateString(undefined, { month: "long" });
const dayParts = (iso: string) => {
  const d = new Date(iso.slice(0, 10) + "T00:00:00");
  return { day: d.getDate(), wk: d.toLocaleDateString(undefined, { weekday: "short" }), mon: d.toLocaleDateString(undefined, { month: "short" }) };
};

export function HolidaysConfigPage() {
  const [rows, setRows] = useState<Holiday[]>([]);
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [cat, setCat] = useState<string>("all");
  const [form, setForm] = useState<FormState>(blankForm(new Date().getFullYear()));
  const [editingId, setEditingId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [formError, setFormError] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      setRows(await api.getHolidays(year));
    } catch (err: any) {
      setRows([]);
      setStatus({ text: err?.message || "Failed to load holidays.", ok: false });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [year]);

  const sorted = useMemo(() => [...rows].sort((a, b) => a.HolidayDate.localeCompare(b.HolidayDate)), [rows]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    rows.forEach((r) => { c[r.Category] = (c[r.Category] || 0) + 1; });
    return c;
  }, [rows]);
  const visible = sorted.filter((r) => cat === "all" || r.Category === cat);
  const byMonth = useMemo(() => {
    const groups: { key: string; name: string; items: Holiday[] }[] = [];
    visible.forEach((r) => {
      const key = r.HolidayDate.slice(0, 7);
      let g = groups.find((x) => x.key === key);
      if (!g) { g = { key, name: monthName(r.HolidayDate), items: [] }; groups.push(g); }
      g.items.push(r);
    });
    return groups;
  }, [visible]);

  const nextUp = useMemo(() => sorted.find((r) => r.IsActive === "Y" && r.HolidayDate.slice(0, 10) >= todayIso()), [sorted]);

  const openNew = () => { setEditingId(null); setForm(blankForm(year)); setFormError(""); setOpen(true); };
  const openEdit = (r: Holiday) => {
    setEditingId(r.HolidayId);
    setForm({ HolidayDate: r.HolidayDate.slice(0, 10), HolidayName: r.HolidayName, Category: r.Category, IsActive: r.IsActive ?? "Y" });
    setFormError("");
    setOpen(true);
  };
  const close = () => { setOpen(false); setEditingId(null); setFormError(""); };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setFormError("");
    if (!form.HolidayName.trim()) { setFormError("Enter the holiday name."); return; }
    if (!form.HolidayDate) { setFormError("Choose the date."); return; }
    const payload = { HolidayDate: form.HolidayDate, HolidayName: form.HolidayName.trim(), Category: form.Category, IsActive: form.IsActive ?? "Y" };
    setSaving(true);
    try {
      if (editingId === null) await api.createHoliday(payload);
      else await api.updateHoliday(editingId, payload);
      setStatus({ text: editingId === null ? "Holiday added." : "Holiday updated.", ok: true });
      // Jump to the year the holiday was saved in so it is visible straight away.
      const savedYear = Number(form.HolidayDate.slice(0, 4));
      close();
      if (savedYear && savedYear !== year) setYear(savedYear); else await load();
    } catch (err: any) {
      setFormError(err?.message || "Failed to save holiday.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (r: Holiday) => {
    if (!window.confirm(`Delete "${r.HolidayName}"?`)) return;
    try {
      await api.deleteHoliday(r.HolidayId);
      setStatus({ text: "Holiday deleted.", ok: true });
      await load();
    } catch (err: any) {
      setStatus({ text: err?.message || "Failed to delete holiday.", ok: false });
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Holidays</h2>
          <p className="sub">Public holidays, company holidays and weekly offs. They are not counted as absent in attendance and payroll.</p>
        </div>
        <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ Add holiday</button>
      </div>

      <Flash status={status} />

      <div className="hol-bar">
        <div className="hol-year" role="group" aria-label="Year">
          <button type="button" onClick={() => setYear(year - 1)} aria-label="Previous year">‹</button>
          <strong>{year}</strong>
          <button type="button" onClick={() => setYear(year + 1)} aria-label="Next year">›</button>
        </div>
        <div className="cfg-stats" style={{ margin: 0 }}>
          <button type="button" className={"cfg-stat" + (cat === "all" ? " on" : "")} onClick={() => setCat("all")} aria-pressed={cat === "all"}>
            <b>{rows.length}</b><span>All</span>
          </button>
          {CATEGORIES.map((c) => (
            <button key={c.value} type="button" className={"cfg-stat" + (cat === c.value ? " on" : "")} onClick={() => setCat(cat === c.value ? "all" : c.value)} aria-pressed={cat === c.value}>
              <b>{counts[c.value] || 0}</b><span>{c.label}</span>
            </button>
          ))}
        </div>
      </div>

      {nextUp && year === new Date().getFullYear() && (
        <div className="hol-next">
          <span className="hol-next-label">Next holiday</span>
          <strong>{nextUp.HolidayName}</strong>
          <span>{new Date(nextUp.HolidayDate.slice(0, 10) + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</span>
        </div>
      )}

      {!loading && visible.length === 0 ? (
        <div className="section-card cfg-empty">
          <strong>{rows.length === 0 ? `No holidays for ${year}` : "Nothing in this category"}</strong>
          <span>{rows.length === 0 ? "Add the public and company holidays so they are not counted as absent." : "Choose All to see every holiday."}</span>
          {rows.length === 0 && <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ Add holiday</button>}
        </div>
      ) : (
        byMonth.map((g) => (
          <section key={g.key} className="hol-month">
            <h3>{g.name}</h3>
            <div className="hol-list">
              {g.items.map((r) => {
                const p = dayParts(r.HolidayDate);
                const c = catOf(r.Category);
                return (
                  <div key={r.HolidayId} className={"hol-row" + (r.IsActive === "Y" ? "" : " is-inactive")}>
                    <div className="hol-date" aria-hidden><b>{p.day}</b><span>{p.mon}</span></div>
                    <div className="hol-body">
                      <strong>{r.HolidayName}</strong>
                      <span className="sd-sub">{p.wk}</span>
                    </div>
                    <span className={"badge " + c.badge}>{c.label}</span>
                    {r.IsActive !== "Y" && <span className="badge badge-red">Inactive</span>}
                    <div className="cfg-actions">
                      <button type="button" className="btn btn-outline-reports" onClick={() => openEdit(r)}>Edit</button>
                      <button type="button" className="btn btn-outline-reports shift-delete" onClick={() => handleDelete(r)}>Delete</button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ))
      )}

      {open && (
        <ConfigModal
          title={editingId === null ? "Add holiday" : "Edit holiday"}
          subtitle={form.HolidayName || "Pick a date and give it a name"}
          icon={Icons.holiday}
          onClose={close} onSubmit={handleSubmit} error={formError} saving={saving}
          submitLabel={editingId === null ? "Add holiday" : "Save changes"}
        >
          <section className="emp-section">
            <SectionHead icon={Icons.calendar} title="Holiday" desc="What it is and when it falls" />
            <div className="emp-grid">
              <div className="field field-span-2">
                <label htmlFor="ho-name">Holiday name <Req /></label>
                <input id="ho-name" value={form.HolidayName} placeholder="e.g. Independence Day" onChange={(e) => setForm({ ...form, HolidayName: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="ho-date">Date <Req /></label>
                <input id="ho-date" type="date" value={form.HolidayDate} onChange={(e) => setForm({ ...form, HolidayDate: e.target.value })} />
              </div>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.tag} title="Type" desc="Helps you filter and report" />
            <div className="cat-cards" role="radiogroup" aria-label="Holiday type">
              {CATEGORIES.map((c) => (
                <button key={c.value} type="button" role="radio" aria-checked={form.Category === c.value}
                  className={"cat-card" + (form.Category === c.value ? " on" : "")} onClick={() => setForm({ ...form, Category: c.value })}>
                  <strong>{c.label}</strong><span>{c.help}</span>
                </button>
              ))}
            </div>
            <div style={{ marginTop: 18 }}>
              <span className="field-label">Status</span>
              <Segmented label="Status" value={form.IsActive ?? "Y"} onChange={(v) => setForm({ ...form, IsActive: v })} options={[["Y", "Active"], ["N", "Inactive"]]} />
            </div>
          </section>
        </ConfigModal>
      )}
    </div>
  );
}
