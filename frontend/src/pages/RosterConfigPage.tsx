import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import { ConfigModal, Flash, SectionHead, Segmented, fmtDate } from "../components/ConfigUi";
import { Req } from "../components/Req";
import { Icons } from "../components/SidebarIcons";

type Roster = {
  ShiftRosterId: number;
  EmployeeCode: string;
  ShiftId: number;
  FromDate: string;
  ToDate?: string | null;
};

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

type Phase = "current" | "upcoming" | "ended";
const phaseOf = (r: Roster): Phase => {
  const t = todayIso();
  const from = r.FromDate.slice(0, 10);
  const to = r.ToDate ? r.ToDate.slice(0, 10) : null;
  if (from > t) return "upcoming";
  if (to && to < t) return "ended";
  return "current";
};
const PHASE_LABEL: Record<Phase, string> = { current: "Current", upcoming: "Upcoming", ended: "Ended" };
const PHASE_BADGE: Record<Phase, string> = { current: "badge-green", upcoming: "badge-blue", ended: "badge-gray" };

type FormState = { EmployeeCode: string; ShiftId: string; FromDate: string; hasEnd: boolean; ToDate: string };
const blankForm = (): FormState => ({ EmployeeCode: "", ShiftId: "", FromDate: todayIso(), hasEnd: false, ToDate: "" });

export function RosterConfigPage() {
  const [rows, setRows] = useState<Roster[]>([]);
  const [shifts, setShifts] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [form, setForm] = useState<FormState>(blankForm());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [formError, setFormError] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [phase, setPhase] = useState<"all" | Phase>("all");

  const load = async () => {
    try {
      setLoading(true);
      setRows(await api.getRosters());
    } catch (err: any) {
      setRows([]);
      setStatus({ text: err?.message || "Failed to load rosters.", ok: false });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    api.getShifts().then(setShifts).catch(() => setShifts([]));
    api.getEmployees().then(setEmployees).catch(() => setEmployees([]));
  }, []);

  const shiftById = useMemo(() => new Map(shifts.map((s) => [s.ShiftId, s])), [shifts]);
  const empByCode = useMemo(() => new Map(employees.map((e) => [String(e.EmployeeCode), e])), [employees]);

  const counts = useMemo(() => {
    const c = { current: 0, upcoming: 0, ended: 0 };
    rows.forEach((r) => { c[phaseOf(r)] += 1; });
    return c;
  }, [rows]);

  const visible = rows.filter((r) => {
    if (phase !== "all" && phaseOf(r) !== phase) return false;
    const q = search.trim().toLowerCase();
    if (!q) return true;
    const e = empByCode.get(r.EmployeeCode);
    return r.EmployeeCode.toLowerCase().includes(q) || (e?.EmployeeName || "").toLowerCase().includes(q);
  });

  const openNew = () => { setEditingId(null); setForm(blankForm()); setFormError(""); setOpen(true); };
  const openEdit = (r: Roster) => {
    setEditingId(r.ShiftRosterId);
    setForm({
      EmployeeCode: r.EmployeeCode,
      ShiftId: String(r.ShiftId),
      FromDate: r.FromDate.slice(0, 10),
      hasEnd: !!r.ToDate,
      ToDate: r.ToDate ? r.ToDate.slice(0, 10) : "",
    });
    setFormError("");
    setOpen(true);
  };
  const close = () => { setOpen(false); setEditingId(null); setFormError(""); };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setFormError("");
    if (!form.EmployeeCode) { setFormError("Choose an employee."); return; }
    if (!form.ShiftId) { setFormError("Choose a shift."); return; }
    if (!form.FromDate) { setFormError("Choose the start date."); return; }
    if (form.hasEnd && !form.ToDate) { setFormError("Choose the end date, or select No end date."); return; }
    if (form.hasEnd && form.ToDate < form.FromDate) { setFormError("The end date is before the start date."); return; }
    const payload = {
      EmployeeCode: form.EmployeeCode,
      ShiftId: Number(form.ShiftId),
      FromDate: form.FromDate,
      ToDate: form.hasEnd ? form.ToDate : null,
    };
    setSaving(true);
    try {
      if (editingId === null) await api.createRoster(payload);
      else await api.updateRoster(editingId, payload);
      setStatus({ text: editingId === null ? "Roster entry added." : "Roster entry updated.", ok: true });
      close();
      await load();
    } catch (err: any) {
      setFormError(err?.message || "Failed to save roster entry.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (r: Roster) => {
    const e = empByCode.get(r.EmployeeCode);
    if (!window.confirm(`Remove ${e?.EmployeeName || r.EmployeeCode} from this shift assignment?`)) return;
    try {
      await api.deleteRoster(r.ShiftRosterId);
      setStatus({ text: "Roster entry deleted.", ok: true });
      await load();
    } catch (err: any) {
      setStatus({ text: err?.message || "Failed to delete roster entry.", ok: false });
    }
  };

  const selectedShift = shiftById.get(Number(form.ShiftId));

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Rosters</h2>
          <p className="sub">Assign employees to shifts for a date range. Anyone without an assignment uses the default shift.</p>
        </div>
        <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ Assign shift</button>
      </div>

      <Flash status={status} />

      <div className="cfg-stats">
        {(["current", "upcoming", "ended"] as Phase[]).map((p) => (
          <button key={p} type="button" className={"cfg-stat" + (phase === p ? " on" : "")} onClick={() => setPhase(phase === p ? "all" : p)} aria-pressed={phase === p}>
            <b>{counts[p]}</b><span>{PHASE_LABEL[p]}</span>
          </button>
        ))}
      </div>

      <div className="section-card cfg-table-card">
        <div className="cfg-toolbar">
          <input type="search" className="cfg-search" placeholder="Search employee name or code" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search rosters" />
          <span className="cfg-count">{visible.length} of {rows.length}</span>
        </div>

        {!loading && visible.length === 0 ? (
          <div className="cfg-empty">
            {rows.length === 0 ? (
              <>
                <strong>No roster entries yet</strong>
                <span>Assign a shift to an employee to override the default shift for a date range.</span>
                <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ Assign shift</button>
              </>
            ) : <><strong>Nothing matches</strong><span>Try a different search or clear the status filter.</span></>}
          </div>
        ) : (
          <table className="table cfg-table">
            <thead>
              <tr><th>Employee</th><th>Shift</th><th>Period</th><th>Status</th><th /></tr>
            </thead>
            <tbody>
              {visible.map((r) => {
                const e = empByCode.get(r.EmployeeCode);
                const s = shiftById.get(r.ShiftId);
                const p = phaseOf(r);
                return (
                  <tr key={r.ShiftRosterId}>
                    <td>
                      <div className="cfg-person">
                        <span className="cfg-avatar" aria-hidden>{(e?.EmployeeName || r.EmployeeCode).trim().charAt(0).toUpperCase()}</span>
                        <div><strong>{e?.EmployeeName || "Unknown employee"}</strong><div className="sd-sub">{r.EmployeeCode}</div></div>
                      </div>
                    </td>
                    <td>{s ? <><strong>{s.ShiftName}</strong><div className="sd-sub">{s.StartTime} – {s.EndTime}</div></> : <span className="sd-sub">Shift #{r.ShiftId} (removed)</span>}</td>
                    <td>{fmtDate(r.FromDate)} <span className="cfg-arrow">→</span> {r.ToDate ? fmtDate(r.ToDate) : <span className="badge badge-purple">No end date</span>}</td>
                    <td><span className={"badge " + PHASE_BADGE[p]}>{PHASE_LABEL[p]}</span></td>
                    <td className="cfg-actions">
                      <button type="button" className="btn btn-outline-reports" onClick={() => openEdit(r)}>Edit</button>
                      <button type="button" className="btn btn-outline-reports shift-delete" onClick={() => handleDelete(r)}>Delete</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {open && (
        <ConfigModal
          title={editingId === null ? "Assign shift" : "Edit assignment"}
          subtitle="Choose who, which shift and for how long"
          icon={Icons.roster}
          onClose={close} onSubmit={handleSubmit} error={formError} saving={saving}
          submitLabel={editingId === null ? "Assign shift" : "Save changes"}
        >
          <section className="emp-section">
            <SectionHead icon={Icons.employees} title="Who and which shift" desc="The shift replaces the default for this person" />
            <div className="emp-grid">
              <div className="field field-span-2">
                <label htmlFor="ro-emp">Employee <Req /></label>
                <select id="ro-emp" value={form.EmployeeCode} onChange={(e) => setForm({ ...form, EmployeeCode: e.target.value })}>
                  <option value="">Select employee…</option>
                  {form.EmployeeCode && !empByCode.has(form.EmployeeCode) && <option value={form.EmployeeCode}>{form.EmployeeCode}</option>}
                  {employees.map((e) => <option key={e.EmployeeId} value={e.EmployeeCode}>{e.EmployeeName} ({e.EmployeeCode})</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="ro-shift">Shift <Req /></label>
                <select id="ro-shift" value={form.ShiftId} onChange={(e) => setForm({ ...form, ShiftId: e.target.value })}>
                  <option value="">Select shift…</option>
                  {shifts.filter((s) => s.IsActive === "Y" || String(s.ShiftId) === form.ShiftId)
                    .map((s) => <option key={s.ShiftId} value={s.ShiftId}>{s.ShiftName} ({s.StartTime}–{s.EndTime})</option>)}
                </select>
                {selectedShift && <span className="field-hint">{selectedShift.StartTime} – {selectedShift.EndTime}</span>}
              </div>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.calendar} title="Period" desc="When this assignment applies" />
            <div className="hours-row">
              <div>
                <label className="field-label" htmlFor="ro-from">Starts <Req /></label>
                <input id="ro-from" type="date" value={form.FromDate} onChange={(e) => setForm({ ...form, FromDate: e.target.value })} required />
              </div>
              <div>
                <span className="field-label">Ends</span>
                <Segmented label="End date" value={form.hasEnd ? "date" : "none"} onChange={(v) => setForm({ ...form, hasEnd: v === "date" })}
                  options={[["none", "No end date"], ["date", "On a date"]]} />
              </div>
              {form.hasEnd && (
                <div>
                  <label className="field-label" htmlFor="ro-to">End date <Req /></label>
                  <input id="ro-to" type="date" value={form.ToDate} min={form.FromDate} onChange={(e) => setForm({ ...form, ToDate: e.target.value })} />
                </div>
              )}
            </div>
          </section>
        </ConfigModal>
      )}
    </div>
  );
}
