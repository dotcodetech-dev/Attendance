import { FormEvent, useState } from "react";

import { api } from "../api/client";
import { ConfigModal, Flash, SectionHead, Segmented, TimeField, fmtDate } from "../components/ConfigUi";
import { EmployeeSearch, useEmployees } from "../components/EmployeeSelect";
import { Icons } from "../components/SidebarIcons";
import { Req } from "../components/Req";

type ManualEntryRow = {
  ManualEntryId: number;
  EmployeeCode: string;
  LogDate: string;
  EntryType: "Manual" | "OD";
  InTime?: string | null;
  OutTime?: string | null;
  Reason?: string | null;
  Status: string;
  AppliedAt: string;
};

const todayIso = () => new Date().toISOString().slice(0, 10);

type FormState = { EmployeeCode: string; LogDate: string; EntryType: "Manual" | "OD"; InTime: string; OutTime: string; Reason: string };
const blankForm = (code = ""): FormState => ({ EmployeeCode: code, LogDate: todayIso(), EntryType: "Manual", InTime: "", OutTime: "", Reason: "" });

const statusBadge = (s: string) => {
  const v = s.toLowerCase();
  if (v.startsWith("approv")) return "badge-green";
  if (v.startsWith("reject")) return "badge-red";
  return "badge-amber";
};

export function EssManualEntryPage() {
  const employees = useEmployees();
  const [employeeCodeFilter, setEmployeeCodeFilter] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [form, setForm] = useState<FormState>(blankForm());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<ManualEntryRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [formError, setFormError] = useState("");

  const load = async (codeArg?: string) => {
    const employeeCode = (codeArg ?? employeeCodeFilter).trim();
    if (!employeeCode) { setRows([]); setLoaded(false); return; }
    try {
      setLoading(true);
      setStatus(null);
      const data = await api.getMyManualEntries({
        employee_code: employeeCode,
        from_date: fromDate ? `${fromDate}T00:00:00` : undefined,
        to_date: toDate ? `${toDate}T23:59:59` : undefined,
      });
      setRows(data);
      setLoaded(true);
    } catch (err: any) {
      setRows([]);
      setLoaded(false);
      setStatus({ text: err?.message || "Failed to load manual entries.", ok: false });
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (event: FormEvent) => { event.preventDefault(); await load(); };
  const pickEmployee = (code: string) => { setEmployeeCodeFilter(code); load(code); };

  const openNew = () => { setEditingId(null); setForm(blankForm(employeeCodeFilter)); setFormError(""); setOpen(true); };
  const openEdit = (row: ManualEntryRow) => {
    setEditingId(row.ManualEntryId);
    setForm({
      EmployeeCode: row.EmployeeCode, LogDate: row.LogDate.slice(0, 10), EntryType: row.EntryType,
      InTime: row.InTime ?? "", OutTime: row.OutTime ?? "", Reason: row.Reason ?? "",
    });
    setFormError("");
    setOpen(true);
  };
  const close = () => { setOpen(false); setEditingId(null); setFormError(""); };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setFormError("");
    if (!form.EmployeeCode) { setFormError("Choose an employee."); return; }
    if (!form.LogDate) { setFormError("Choose the date."); return; }
    if (form.EntryType === "Manual" && !form.InTime && !form.OutTime) { setFormError("Enter an in time, an out time, or both."); return; }
    const payload = {
      EmployeeCode: form.EmployeeCode.trim(),
      LogDate: `${form.LogDate}T00:00:00`,
      EntryType: form.EntryType,
      InTime: form.InTime || null,
      OutTime: form.OutTime || null,
      Reason: form.Reason.trim() || null,
    };
    setSaving(true);
    try {
      if (editingId === null) await api.applyManualEntry(payload);
      else await api.updateManualEntry(editingId, payload);
      setStatus({ text: editingId === null ? "Request submitted." : "Request updated.", ok: true });
      setEmployeeCodeFilter(payload.EmployeeCode);
      close();
      await load(payload.EmployeeCode);
    } catch (err: any) {
      setFormError(err?.message || "Failed to save the request.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm("Delete this request?")) return;
    try {
      await api.deleteManualEntry(id);
      setStatus({ text: "Request deleted.", ok: true });
      await load();
    } catch (err: any) {
      setStatus({ text: err?.message || "Failed to delete the request.", ok: false });
    }
  };

  const nameOf = (code: string) => employees.find((e) => String(e.EmployeeCode) === code)?.EmployeeName;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Manual Entry / OD</h2>
          <p className="sub">Correct a missed punch, or record time spent on duty away from the office (OD). Requests wait for approval.</p>
        </div>
        <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ New request</button>
      </div>

      <form onSubmit={handleSearch} className="section-card ess-filter">
        <div className="hours-row" style={{ marginBottom: 0 }}>
          <div style={{ flex: "1 1 280px", minWidth: 0 }}>
            <label className="field-label" htmlFor="me-emp">Employee <Req /></label>
            <EmployeeSearch id="me-emp" employees={employees} value={employeeCodeFilter} onChange={(c) => (c ? pickEmployee(c) : setEmployeeCodeFilter(""))} style={{ width: "100%" }} />
          </div>
          <div>
            <label className="field-label" htmlFor="me-from">From</label>
            <input id="me-from" type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
          </div>
          <div>
            <label className="field-label" htmlFor="me-to">To</label>
            <input id="me-to" type="date" min={fromDate} value={toDate} onChange={(e) => setToDate(e.target.value)} />
          </div>
          <button type="submit" className="btn btn-outline-reports" disabled={loading || !employeeCodeFilter}>{loading ? "Loading…" : "Apply filter"}</button>
        </div>
      </form>

      <Flash status={status} />

      {!loaded ? (
        <div className="section-card cfg-empty">
          <strong>Choose an employee</strong>
          <span>Their manual entries and OD requests will be listed here.</span>
        </div>
      ) : (
        <div className="section-card cfg-table-card">
          <div className="cfg-toolbar"><strong>{nameOf(employeeCodeFilter) || employeeCodeFilter}</strong><span className="cfg-count">{rows.length} request{rows.length === 1 ? "" : "s"}</span></div>
          {rows.length === 0 ? (
            <div className="cfg-empty">
              <strong>No requests found</strong><span>Try a wider date range, or create a new request.</span>
              <button type="button" className="btn btn-primary-purple" onClick={openNew}>+ New request</button>
            </div>
          ) : (
            <table className="table cfg-table">
              <thead><tr><th>Date</th><th>Type</th><th>In</th><th>Out</th><th>Reason</th><th>Status</th><th /></tr></thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.ManualEntryId}>
                    <td><strong>{fmtDate(row.LogDate)}</strong></td>
                    <td><span className={"badge " + (row.EntryType === "OD" ? "badge-blue" : "badge-purple")}>{row.EntryType === "OD" ? "On duty" : "Manual"}</span></td>
                    <td className="cfg-time">{row.InTime || "—"}</td>
                    <td className="cfg-time">{row.OutTime || "—"}</td>
                    <td>{row.Reason || "—"}</td>
                    <td><span className={"badge " + statusBadge(row.Status)}>{row.Status}</span></td>
                    <td className="cfg-actions">
                      <button type="button" className="btn btn-outline-reports" onClick={() => openEdit(row)}>Edit</button>
                      <button type="button" className="btn btn-outline-reports shift-delete" onClick={() => handleDelete(row.ManualEntryId)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {open && (
        <ConfigModal
          title={editingId === null ? "New request" : "Edit request"}
          subtitle="Manual punch correction or on-duty time"
          icon={Icons.edit}
          onClose={close} onSubmit={handleSubmit} error={formError} saving={saving}
          submitLabel={editingId === null ? "Submit request" : "Save changes"}
        >
          <section className="emp-section">
            <SectionHead icon={Icons.employees} title="Who and when" desc="The person and the day this applies to" />
            <div className="emp-grid">
              <div className="field field-span-2">
                <label htmlFor="mf-emp">Employee <Req /></label>
                <EmployeeSearch id="mf-emp" employees={employees} value={form.EmployeeCode} onChange={(c) => setForm({ ...form, EmployeeCode: c })} />
              </div>
              <div className="field">
                <label htmlFor="mf-date">Date <Req /></label>
                <input id="mf-date" type="date" value={form.LogDate} onChange={(e) => setForm({ ...form, LogDate: e.target.value })} />
              </div>
            </div>
            <div style={{ marginTop: 20 }}>
              <span className="field-label">Type</span>
              <Segmented label="Request type" value={form.EntryType} onChange={(v) => setForm({ ...form, EntryType: v as "Manual" | "OD" })}
                options={[["Manual", "Manual entry"], ["OD", "On duty (OD)"]]} />
              <span className="field-hint" style={{ display: "block", marginTop: 8 }}>
                {form.EntryType === "Manual" ? "Use this to fix a missed or wrong punch." : "Use this when the person worked away from the office."}
              </span>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.calendar} title="Times" desc="In time, out time, or both. An on-duty request may leave them empty for a full day." />
            <div className="hours-row" style={{ marginBottom: 20 }}>
              <div>
                <label className="field-label" htmlFor="mf-in">In time</label>
                <TimeField id="mf-in" label="In time" value={form.InTime} onChange={(v) => setForm({ ...form, InTime: v })} />
              </div>
              <span className="meal-to">to</span>
              <div>
                <label className="field-label" htmlFor="mf-out">Out time</label>
                <TimeField id="mf-out" label="Out time" value={form.OutTime} onChange={(v) => setForm({ ...form, OutTime: v })} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="mf-reason">Reason</label>
              <input id="mf-reason" style={{ width: "100%" }} value={form.Reason} placeholder="Optional. Helps the approver decide." onChange={(e) => setForm({ ...form, Reason: e.target.value })} />
            </div>
          </section>
        </ConfigModal>
      )}
    </div>
  );
}
