import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import { ConfigModal, Flash, NumField, SectionHead, Segmented, SwitchRow } from "../components/ConfigUi";
import { Req } from "../components/Req";
import { Icons } from "../components/SidebarIcons";

type LeaveConfig = {
  LeaveConfigId: number;
  Code: string;
  Name: string;
  MaxPerYear?: number | null;
  IsPaid?: string | null;
  ConsiderWeeklyOff?: string | null;
  ConsiderHoliday?: string | null;
  CarryForwardLimit?: number | null;
  IsActive?: string | null;
};

type FormState = Omit<LeaveConfig, "LeaveConfigId">;

const blankForm: FormState = {
  Code: "",
  Name: "",
  MaxPerYear: 0,
  IsPaid: "Y",
  ConsiderWeeklyOff: "N",
  ConsiderHoliday: "N",
  CarryForwardLimit: 0,
  IsActive: "Y",
};

const on = (v?: string | null) => (v ?? "N") === "Y";
const days = (n?: number | null) => `${n ?? 0} day${(n ?? 0) === 1 ? "" : "s"}`;

export function LeavesConfigPage() {
  const [rows, setRows] = useState<LeaveConfig[]>([]);
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
      setRows(await api.getLeaveConfigs());
    } catch (err: any) {
      setRows([]);
      setStatus({ text: err?.message || "Failed to load leave types.", ok: false });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((p) => ({ ...p, [key]: value }));

  const openNew = () => { setEditingId(null); setForm(blankForm); setFormError(""); setOpen(true); };
  const openEdit = (row: LeaveConfig) => {
    setEditingId(row.LeaveConfigId);
    setForm({
      Code: row.Code,
      Name: row.Name,
      MaxPerYear: row.MaxPerYear ?? 0,
      IsPaid: row.IsPaid ?? "Y",
      ConsiderWeeklyOff: row.ConsiderWeeklyOff ?? "N",
      ConsiderHoliday: row.ConsiderHoliday ?? "N",
      CarryForwardLimit: row.CarryForwardLimit ?? 0,
      IsActive: row.IsActive ?? "Y",
    });
    setFormError("");
    setOpen(true);
  };
  const close = () => { setOpen(false); setEditingId(null); setFormError(""); };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setFormError("");
    const payload = {
      Code: form.Code.trim(),
      Name: form.Name.trim(),
      MaxPerYear: form.MaxPerYear ?? 0,
      IsPaid: form.IsPaid ?? "Y",
      ConsiderWeeklyOff: form.ConsiderWeeklyOff ?? "N",
      ConsiderHoliday: form.ConsiderHoliday ?? "N",
      CarryForwardLimit: form.CarryForwardLimit ?? 0,
      IsActive: form.IsActive ?? "Y",
    };
    if (!payload.Code) { setFormError("Enter a short code, for example CL."); return; }
    if (!payload.Name) { setFormError("Enter the leave type name."); return; }
    setSaving(true);
    try {
      if (editingId === null) await api.createLeaveConfig(payload);
      else await api.updateLeaveConfig(editingId, payload);
      setStatus({ text: editingId === null ? "Leave type created." : "Leave type updated.", ok: true });
      close();
      await load();
    } catch (err: any) {
      setFormError(err?.message || "Failed to save leave type.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (row: LeaveConfig) => {
    if (!window.confirm(`Delete the leave type "${row.Name}"?`)) return;
    try {
      await api.deleteLeaveConfig(row.LeaveConfigId);
      setStatus({ text: "Leave type deleted.", ok: true });
      await load();
    } catch (err: any) {
      setStatus({ text: err?.message || "Failed to delete leave type.", ok: false });
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Leave Types</h2>
          <p className="sub">Leave codes such as CL, SL and PL, their yearly entitlement, and how weekly offs and holidays are counted.</p>
        </div>
        <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ New leave type</button>
      </div>

      <Flash status={status} />

      {!loading && rows.length === 0 ? (
        <div className="section-card cfg-empty">
          <strong>No leave types yet</strong>
          <span>Add types like Casual Leave and Sick Leave so employees can apply for them.</span>
          <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ New leave type</button>
        </div>
      ) : (
        <div className="shift-grid">
          {rows.map((row) => {
            const inactive = row.IsActive !== "Y";
            return (
              <article key={row.LeaveConfigId} className={"shift-card" + (inactive ? " is-inactive" : "")}>
                <header className="lt-head">
                  <span className="lt-code">{row.Code}</span>
                  <div>
                    <h3>{row.Name}</h3>
                    <div className="shift-badges">
                      <span className={"badge " + (on(row.IsPaid) ? "badge-green" : "badge-gray")}>{on(row.IsPaid) ? "Paid" : "Unpaid"}</span>
                      {inactive && <span className="badge badge-red">Inactive</span>}
                    </div>
                  </div>
                </header>
                <div className="shift-time">
                  <strong>{row.MaxPerYear ? days(row.MaxPerYear) : "Unlimited"}</strong>
                  <span>{row.MaxPerYear ? "per year" : "no yearly limit"}</span>
                </div>
                <dl className="shift-stats">
                  <div><dt>Carry forward</dt><dd>{row.CarryForwardLimit ? `Up to ${days(row.CarryForwardLimit)}` : "None"}</dd></div>
                  <div><dt>Weekly offs in leave</dt><dd>{on(row.ConsiderWeeklyOff) ? "Counted" : "Skipped"}</dd></div>
                  <div><dt>Holidays in leave</dt><dd>{on(row.ConsiderHoliday) ? "Counted" : "Skipped"}</dd></div>
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

      <EmployeeBalanceEditor />

      {open && (
        <ConfigModal
          title={editingId === null ? "New leave type" : "Edit leave type"}
          subtitle={form.Name ? `${form.Name}${form.Code ? ` (${form.Code})` : ""}` : "Code, name and entitlement"}
          icon={Icons.leaves}
          onClose={close} onSubmit={handleSubmit} error={formError} saving={saving}
          submitLabel={editingId === null ? "Create leave type" : "Save changes"}
        >
          <section className="emp-section">
            <SectionHead icon={Icons.tag} title="Basics" desc="How it is named and shown" />
            <div className="emp-grid">
              <div className="field">
                <label htmlFor="lt-code">Code <Req /></label>
                <input id="lt-code" value={form.Code} maxLength={10} placeholder="e.g. CL" onChange={(e) => set("Code", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="lt-name">Name <Req /></label>
                <input id="lt-name" value={form.Name} placeholder="e.g. Casual Leave" onChange={(e) => set("Name", e.target.value)} />
              </div>
              <div className="field">
                <label>Status</label>
                <Segmented label="Status" value={form.IsActive ?? "Y"} onChange={(v) => set("IsActive", v)} options={[["Y", "Active"], ["N", "Inactive"]]} />
              </div>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.calendar} title="Entitlement" desc="How much leave each person gets" />
            <div className="rule-grid">
              <div>
                <label className="field-label" htmlFor="lt-max">Days per year</label>
                <NumField id="lt-max" max={365} suffix="days" value={form.MaxPerYear ?? 0} onChange={(v) => set("MaxPerYear", v)} />
                <span className="field-hint">Enter 0 for no yearly limit.</span>
              </div>
              <div>
                <label className="field-label" htmlFor="lt-cf">Carry forward up to</label>
                <NumField id="lt-cf" max={365} suffix="days" value={form.CarryForwardLimit ?? 0} onChange={(v) => set("CarryForwardLimit", v)} />
                <span className="field-hint">Unused days moved to next year.</span>
              </div>
              <div>
                <span className="field-label">Pay</span>
                <Segmented label="Pay" value={form.IsPaid ?? "Y"} onChange={(v) => set("IsPaid", v)} options={[["Y", "Paid"], ["N", "Unpaid"]]} />
                <span className="field-hint">Unpaid leave reduces salary days.</span>
              </div>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.holiday} title="Counting rules" desc="What happens when a leave spans days off" />
            <div className="switch-list" style={{ marginTop: 0, paddingTop: 0, borderTop: 0 }}>
              <SwitchRow id="lt-wo" checked={on(form.ConsiderWeeklyOff)} onChange={(v) => set("ConsiderWeeklyOff", v ? "Y" : "N")}
                title="Count weekly offs inside a leave" desc="Off: a Friday to Monday leave skips the weekend. On: the weekend is deducted too." />
              <SwitchRow id="lt-hol" checked={on(form.ConsiderHoliday)} onChange={(v) => set("ConsiderHoliday", v ? "Y" : "N")}
                title="Count holidays inside a leave" desc="Off: holidays that fall in the leave are not deducted." />
            </div>
          </section>
        </ConfigModal>
      )}
    </div>
  );
}

function EmployeeBalanceEditor() {
  const [employees, setEmployees] = useState<any[]>([]);
  const [employeeCode, setEmployeeCode] = useState("");
  const [year, setYear] = useState(new Date().getFullYear());
  const [balances, setBalances] = useState<any[]>([]);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.getEmployees().then(setEmployees).catch(() => setEmployees([])); }, []);
  const empName = useMemo(() => employees.find((e) => e.EmployeeCode === employeeCode)?.EmployeeName, [employees, employeeCode]);

  const load = async () => {
    if (!employeeCode.trim()) { setStatus({ text: "Choose an employee first.", ok: false }); return; }
    setLoading(true); setStatus(null);
    try {
      setBalances(await api.getEmployeeLeaveBalance(employeeCode.trim(), year));
    } catch (e: any) {
      setBalances([]);
      setStatus({ text: e?.message || "Failed to load balances.", ok: false });
    } finally { setLoading(false); }
  };

  const save = async (row: any) => {
    try {
      await api.setEmployeeLeaveBalance({
        EmployeeCode: employeeCode.trim(),
        LeaveConfigId: row.LeaveConfigId,
        LeaveYear: year,
        AllowedLeaves: Number(row.AllowedLeaves) || 0,
        CarriedForward: Number(row.CarriedForward) || 0,
      });
      setStatus({ text: `Saved ${row.Code} for ${empName || employeeCode}.`, ok: true });
    } catch (e: any) { setStatus({ text: e?.message || "Save failed.", ok: false }); }
  };

  const seed = async () => {
    if (!window.confirm(`Initialise every employee's ${year} balances from the leave-type defaults? Existing balances are kept.`)) return;
    try {
      const res = await api.seedLeaveBalances(year, false);
      setStatus({ text: `Set up ${res.rows_written} balances across ${res.employees} employees.`, ok: true });
    } catch (e: any) { setStatus({ text: e?.message || "Seed failed.", ok: false }); }
  };

  const edit = (i: number, key: "AllowedLeaves" | "CarriedForward", v: number) =>
    setBalances(balances.map((x, j) => (j === i ? { ...x, [key]: v } : x)));

  return (
    <div className="section-card" style={{ marginTop: 28 }}>
      <p className="section-eyebrow">Employee balances</p>
      <h3 style={{ margin: "0 0 4px", fontSize: 18 }}>Override one person's yearly entitlement</h3>
      <p style={{ margin: "0 0 18px", color: "var(--text-muted)", fontSize: 13.5 }}>
        Set an opening balance and carry-forward for a single employee. If nothing is set, the leave type's default applies.
      </p>

      <div className="hours-row" style={{ marginBottom: 12 }}>
        <div style={{ flex: "1 1 260px", minWidth: 0 }}>
          <label className="field-label" htmlFor="lb-emp">Employee</label>
          <select id="lb-emp" style={{ width: "100%" }} value={employeeCode} onChange={(e) => { setEmployeeCode(e.target.value); setBalances([]); }}>
            <option value="">Select employee…</option>
            {employees.map((e) => <option key={e.EmployeeId} value={e.EmployeeCode}>{e.EmployeeName} ({e.EmployeeCode})</option>)}
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="lb-year">Year</label>
          <input id="lb-year" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
        </div>
        <button type="button" className="btn btn-primary-purple" onClick={load} disabled={loading}>{loading ? "Loading…" : "Load balances"}</button>
        <button type="button" className="btn btn-outline-reports" onClick={seed} title="Initialise all employees for this year">Set up everyone from defaults</button>
      </div>

      <Flash status={status} />

      {balances.length > 0 && (
        <table className="table cfg-table">
          <thead><tr><th>Leave type</th><th>Allowed</th><th>Carried forward</th><th /></tr></thead>
          <tbody>
            {balances.map((b, i) => (
              <tr key={b.LeaveConfigId}>
                <td><span className="lt-code lt-code-sm">{b.Code}</span> {b.Name}</td>
                <td><NumField id={`lb-a-${i}`} max={365} suffix="days" value={Number(b.AllowedLeaves) || 0} onChange={(v) => edit(i, "AllowedLeaves", v)} /></td>
                <td><NumField id={`lb-c-${i}`} max={365} suffix="days" value={Number(b.CarriedForward) || 0} onChange={(v) => edit(i, "CarriedForward", v)} /></td>
                <td className="cfg-actions"><button type="button" className="btn btn-outline-reports" onClick={() => save(b)}>Save</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
