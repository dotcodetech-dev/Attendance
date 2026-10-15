import { useEffect, useState } from "react";

import { api } from "../../api/client";
import { Req } from "../../components/Req";
import { DeptYearFilter, toNum, todayIso, useDepartments } from "./common";

const EMPTY_TYPE = { Code: "", Name: "", MaxPerYear: 0, IsPaid: "Y", IsActive: "Y" };

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
  const [req, setReq] = useState<any>({ StudentCode: "", StudentLeaveConfigId: "", FromDate: todayIso(), ToDate: todayIso(), Reason: "" });
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

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

  const submitRequest = () => run(async () => {
    await api.createStudentLeaveRequest({ ...req, StudentLeaveConfigId: Number(req.StudentLeaveConfigId), Reason: req.Reason || null });
    setReq({ ...req, Reason: "" }); loadRequests();
  }, "Leave request submitted.");

  const decide = (id: number, s: "Approved" | "Rejected") =>
    run(async () => { await api.decideStudentLeave(id, s); loadRequests(); }, `Request ${s.toLowerCase()}.`);

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Student Manual Marking</h2>
          <p className="sub">Leave types and requests for students. Separate from employee leave.</p>
        </div>
      </div>
      {msg && <p className={msg.ok ? "note-ok" : "note-err"}>{msg.text}</p>}

      <div className="section-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Leave Types</h3>
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
        <h3 style={{ marginTop: 0 }}>New Leave Request</h3>
        <div className="form-row-2">
          <DeptYearFilter departments={departments} departmentId={deptFilter} registeredYear={regYearFilter} onDepartment={setDeptFilter} onRegisteredYear={setRegYearFilter} />
          <label><span>Student <Req /></span>
            <select value={req.StudentCode} onChange={(e) => setReq({ ...req, StudentCode: e.target.value })}>
              <option value="">Select…</option>
              {students.map((s) => <option key={s.StudentCode} value={s.StudentCode}>{s.StudentName} ({s.StudentCode})</option>)}
            </select>
          </label>
          <label><span>Leave type <Req /></span>
            <select value={req.StudentLeaveConfigId} onChange={(e) => setReq({ ...req, StudentLeaveConfigId: e.target.value })}>
              <option value="">Select…</option>
              {types.filter((t) => t.IsActive === "Y").map((t) => <option key={t.StudentLeaveConfigId} value={t.StudentLeaveConfigId}>{t.Name}</option>)}
            </select>
          </label>
          <label><span>From <Req /></span><input type="date" value={req.FromDate} onChange={(e) => setReq({ ...req, FromDate: e.target.value })} /></label>
          <label><span>To <Req /></span><input type="date" value={req.ToDate} min={req.FromDate} onChange={(e) => setReq({ ...req, ToDate: e.target.value })} /></label>
          <label>Reason<input value={req.Reason} onChange={(e) => setReq({ ...req, Reason: e.target.value })} /></label>
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-primary-purple" onClick={submitRequest} disabled={!req.StudentCode || !req.StudentLeaveConfigId}>Submit</button>
        </div>
      </div>

      <div className="section-card">
        <div className="form-row-2" style={{ marginBottom: 12 }}>
          <label>Status
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option><option>Pending</option><option>Approved</option><option>Rejected</option>
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
                    <button className="btn-device-ghost" onClick={() => decide(r.StudentLeaveRequestId, "Rejected")}>Reject</button>
                  </>}
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
