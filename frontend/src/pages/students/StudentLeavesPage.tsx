import { useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import { EmployeeSearch } from "../../components/EmployeeSelect";
import { Req } from "../../components/Req";
import { DeptYearFilter, toNum, todayIso, useDepartments } from "./common";

const EMPTY_TYPE = { Code: "", Name: "", MaxPerYear: 0, IsPaid: "Y", IsActive: "Y" };

/** Calendar days from..to inclusive (0 when the range is backwards or incomplete). */
const spanDays = (from: string, to: string) => {
  if (!from || !to) return 0;
  const d = Math.round((new Date(to).getTime() - new Date(from).getTime()) / 86400000);
  return d >= 0 ? d + 1 : 0;
};

const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export function StudentLeavesPage() {
  const departments = useDepartments();
  const [types, setTypes] = useState<any[]>([]);
  const [requests, setRequests] = useState<any[]>([]);
  const [students, setStudents] = useState<any[]>([]);
  const [deptFilter, setDeptFilter] = useState("");
  const [regYearFilter, setRegYearFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeForm, setTypeForm] = useState<any>(EMPTY_TYPE);
  const [editingType, setEditingType] = useState<number | null>(null);
  const [req, setReq] = useState<any>({ StudentCode: "", StudentLeaveConfigId: "", FromDate: todayIso(), ToDate: todayIso(), Reason: "", Approve: true });
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const days = spanDays(req.FromDate, req.ToDate);

  // Students in the shape the type-to-search picker expects (search by name, register no. or roll no.).
  const studentChoices = useMemo(() => {
    const deptName = new Map(departments.map((d: any) => [d.DepartmentId, d.DepartmentName]));
    return students.map((s) => ({
      EmployeeId: s.StudentId ?? s.StudentCode, EmployeeCode: s.StudentCode, EmployeeName: s.StudentName,
      ShortNo: s.RollNo, Department: deptName.get(s.DepartmentId),
    }));
  }, [students, departments]);

  const loadTypes = () => api.getStudentLeaveTypes().then(setTypes).catch((e) => setMsg({ text: e.message, ok: false }));
  const loadRequests = () =>
    api.getStudentLeaveRequests({ status: statusFilter || undefined, department_id: toNum(deptFilter), registered_year: regYearFilter || undefined })
      .then(setRequests).catch((e) => setMsg({ text: e.message, ok: false }));
  useEffect(() => { loadTypes(); }, []);
  useEffect(() => { loadRequests(); }, [deptFilter, regYearFilter, statusFilter]);
  useEffect(() => {
    api.getStudents({ department_id: toNum(deptFilter), registered_year: regYearFilter || undefined }).then(setStudents).catch(() => setStudents([]));
  }, [deptFilter, regYearFilter]);

  const run = async (fn: () => Promise<any>, ok: string) => {
    try { await fn(); setMsg({ text: ok, ok: true }); } catch (e: any) { setMsg({ text: e.message || "Failed", ok: false }); }
  };

  const saveType = () => run(async () => {
    const payload = { ...typeForm, MaxPerYear: Number(typeForm.MaxPerYear) };
    if (editingType) await api.updateStudentLeaveType(editingType, payload);
    else await api.createStudentLeaveType(payload);
    setTypeForm(EMPTY_TYPE); setEditingType(null); loadTypes();
  }, "Leave type saved.");

  const submitRequest = () => {
    const type = types.find((t) => String(t.StudentLeaveConfigId) === String(req.StudentLeaveConfigId));
    const what = `${type?.Code || "Leave"} for ${days} day${days === 1 ? "" : "s"}`;
    return run(async () => {
      await api.createStudentLeaveRequest({ ...req, StudentLeaveConfigId: Number(req.StudentLeaveConfigId), Reason: req.Reason || null });
      setReq({ ...req, Reason: "" }); loadRequests();
    }, req.Approve ? `${what} saved as approved; attendance for those days is updated.` : `${what} submitted for approval.`);
  };

  const decide = (id: number, s: "Approved" | "Rejected") =>
    run(async () => { await api.decideStudentLeave(id, s); loadRequests(); }, `Request ${s.toLowerCase()}.`);

  const cancel = (r: any) => {
    if (!window.confirm(`Cancel ${r.LeaveCode} for ${r.StudentName} (${r.FromDate} to ${r.ToDate})? Attendance for those days is recalculated.`)) return;
    run(async () => { await api.cancelStudentLeave(r.StudentLeaveRequestId); loadRequests(); }, `${r.LeaveCode} cancelled.`);
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Student Manual Marking</h2>
          <p className="sub">Create student leave types (CL, SL, OD …) and enter leave / OD for a student over one or more days. Separate from employee leave.</p>
        </div>
      </div>
      {msg && <p className={msg.ok ? "note-ok" : "note-err"}>{msg.text}</p>}

      <div className="section-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Student Leave Types</h3>
        <p style={{ margin: "0 0 10px", color: "var(--text-muted)", fontSize: 13.5 }}>
          Add a type with the form below (e.g. Code <strong>OD</strong>, Name On Duty, Max per year 0 = unlimited). Edit or deactivate existing types from the list.
        </p>
        <table className="table table-compact">
          <thead><tr><th>Code</th><th>Name</th><th>Max / year</th><th>Paid</th><th>Active</th><th /></tr></thead>
          <tbody>
            {types.map((t) => (
              <tr key={t.StudentLeaveConfigId}>
                <td><strong>{t.Code}</strong></td><td>{t.Name}</td><td>{t.MaxPerYear || "—"}</td><td>{t.IsPaid}</td><td>{t.IsActive}</td>
                <td>
                  <button className="btn-device-ghost" onClick={() => { setEditingType(t.StudentLeaveConfigId); setTypeForm(t); }}>Edit</button>{" "}
                  <button className="btn-device-ghost" onClick={() => run(async () => { await api.deleteStudentLeaveType(t.StudentLeaveConfigId); loadTypes(); }, "Leave type deleted.")}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="form-row-2" style={{ marginTop: 12 }}>
          <label><span>Code <Req /></span><input value={typeForm.Code} maxLength={10} onChange={(e) => setTypeForm({ ...typeForm, Code: e.target.value })} /></label>
          <label><span>Name <Req /></span><input value={typeForm.Name} onChange={(e) => setTypeForm({ ...typeForm, Name: e.target.value })} /></label>
          <label>Max per year (0 = unlimited)<input type="number" min={0} value={typeForm.MaxPerYear} onChange={(e) => setTypeForm({ ...typeForm, MaxPerYear: e.target.value })} /></label>
          <label>Paid
            <select value={typeForm.IsPaid} onChange={(e) => setTypeForm({ ...typeForm, IsPaid: e.target.value })}><option value="Y">Yes</option><option value="N">No</option></select>
          </label>
          <label>Active
            <select value={typeForm.IsActive} onChange={(e) => setTypeForm({ ...typeForm, IsActive: e.target.value })}><option value="Y">Yes</option><option value="N">No</option></select>
          </label>
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button className="btn btn-primary-purple" onClick={saveType} disabled={!typeForm.Code || !typeForm.Name}>{editingType ? "Update type" : "Add type"}</button>
          {editingType && <button className="btn-device-ghost" onClick={() => { setEditingType(null); setTypeForm(EMPTY_TYPE); }}>Cancel</button>}
        </div>
      </div>

      <div className="section-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Enter Leave / OD</h3>
        <div className="form-row-2">
          <DeptYearFilter departments={departments} departmentId={deptFilter} registeredYear={regYearFilter} onDepartment={setDeptFilter} onRegisteredYear={setRegYearFilter} />
          <label><span>Student <Req /></span>
            <EmployeeSearch employees={studentChoices} value={req.StudentCode} placeholder="Type student name, register or roll no…"
              onChange={(c) => setReq({ ...req, StudentCode: c })} />
          </label>
          <label><span>Leave type <Req /></span>
            <select value={req.StudentLeaveConfigId} onChange={(e) => setReq({ ...req, StudentLeaveConfigId: e.target.value })}>
              <option value="">Select…</option>
              {types.filter((t) => t.IsActive === "Y").map((t) => <option key={t.StudentLeaveConfigId} value={t.StudentLeaveConfigId}>{t.Code} · {t.Name}</option>)}
            </select>
          </label>
          <label><span>From <Req /></span><input type="date" value={req.FromDate}
            onChange={(e) => setReq({ ...req, FromDate: e.target.value, ToDate: req.ToDate < e.target.value ? e.target.value : req.ToDate })} /></label>
          <label><span>To <Req /></span><input type="date" value={req.ToDate} min={req.FromDate} onChange={(e) => setReq({ ...req, ToDate: e.target.value })} /></label>
          <label>Reason<input value={req.Reason} placeholder="Optional (e.g. sports meet, seminar)" onChange={(e) => setReq({ ...req, Reason: e.target.value })} /></label>
        </div>
        <div style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Quick:</span>
          {[1, 2, 3].map((n) => (
            <button key={n} type="button" className="btn-device-ghost" onClick={() => setReq({ ...req, ToDate: addDays(req.FromDate, n - 1) })}>
              {n} day{n > 1 ? "s" : ""}
            </button>
          ))}
          <strong style={{ marginLeft: 6 }}>{days ? `${days} day${days === 1 ? "" : "s"}: ${req.FromDate} to ${req.ToDate}` : "Pick valid dates"}</strong>
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12, fontWeight: 500 }}>
          <input type="checkbox" checked={req.Approve} onChange={(e) => setReq({ ...req, Approve: e.target.checked })} />
          Save as approved (no approval step; counts in attendance at once)
        </label>
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-primary-purple" onClick={submitRequest} disabled={!req.StudentCode || !req.StudentLeaveConfigId || !days}>
            {req.Approve ? "Save" : "Submit for approval"}
          </button>
        </div>
      </div>

      <div className="section-card">
        <div className="form-row-2" style={{ marginBottom: 12 }}>
          <label>Status
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option><option>Pending</option><option>Approved</option><option>Rejected</option><option>Cancelled</option>
            </select>
          </label>
        </div>
        <table className="table table-compact">
          <thead><tr><th>Student</th><th>Registered Year</th><th>Type</th><th>From</th><th>To</th><th>Reason</th><th>Status</th><th /></tr></thead>
          <tbody>
            {requests.map((r) => (
              <tr key={r.StudentLeaveRequestId}>
                <td><strong>{r.StudentName}</strong> ({r.StudentCode})</td>
                <td>{r.RegisteredYear}</td><td>{r.LeaveCode}</td><td>{r.FromDate}</td><td>{r.ToDate}</td><td>{r.Reason}</td>
                <td>{r.Status}{r.DecidedBy ? ` · ${r.DecidedBy}` : ""}</td>
                <td>
                  {r.Status === "Pending" && <>
                    <button className="btn-device-ghost" onClick={() => decide(r.StudentLeaveRequestId, "Approved")}>Approve</button>{" "}
                    <button className="btn-device-ghost" onClick={() => decide(r.StudentLeaveRequestId, "Rejected")}>Reject</button>{" "}
                  </>}
                  {(r.Status === "Pending" || r.Status === "Approved") && (
                    <button className="btn-device-ghost" onClick={() => cancel(r)}>Cancel</button>
                  )}
                </td>
              </tr>
            ))}
            {requests.length === 0 && <tr><td colSpan={8} style={{ color: "var(--text-muted)" }}>No requests.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
