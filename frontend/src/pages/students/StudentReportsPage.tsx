import { useState } from "react";

import { api } from "../../api/client";
import { DeptYearFilter, toNum, todayIso, useDepartments } from "./common";

const monthStart = () => todayIso().slice(0, 8) + "01";

export function StudentReportsPage() {
  const departments = useDepartments();
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(todayIso());
  const [deptFilter, setDeptFilter] = useState("");
  const [regYearFilter, setRegYearFilter] = useState("");
  const [rows, setRows] = useState<any[] | null>(null);
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);

  const params = () => ({ from_date: from, to_date: to, department_id: toNum(deptFilter), registered_year: regYearFilter || undefined });

  const run = async () => {
    setLoading(true); setMsg("");
    try { setRows(await api.getStudentReport(params())); } catch (e: any) { setMsg(e.message); } finally { setLoading(false); }
  };
  const download = (fmt: "csv" | "xlsx" | "pdf") => api.downloadStudentReport(fmt, params()).catch((e) => setMsg(e.message));

  // Colour coding mirrors the Employee Attendance Report: green/amber/red by attendance %.
  const pctClass = (p: number | null) =>
    p == null ? "" : p >= 75 ? "att-good" : p >= 60 ? "att-warn" : "att-bad";

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Student Attendance Report</h2>
          <p className="sub">Attendance summary per student, filtered by department and registered year.</p>
        </div>
      </div>
      <div className="section-card">
        <div className="form-row-2" style={{ marginBottom: 12 }}>
          <label>From<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label>To<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
          <DeptYearFilter departments={departments} departmentId={deptFilter} registeredYear={regYearFilter} onDepartment={setDeptFilter} onRegisteredYear={setRegYearFilter} />
        </div>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button className="btn btn-primary-purple" onClick={run} disabled={loading}>{loading ? "Loading…" : "Generate"}</button>
          <button className="btn-device-ghost" onClick={() => download("xlsx")}>Export Excel</button>
          <button className="btn-device-ghost" onClick={() => download("pdf")}>Export PDF</button>
          <button className="btn-device-ghost" onClick={() => download("csv")}>Export CSV</button>
          <button className="btn-device-ghost" onClick={() => window.print()}>Print</button>
        </div>
        {msg && <p className="note-err">{msg}</p>}
        {rows && (
          <table className="table table-compact student-report">
            <thead><tr><th>Code</th><th>Name</th><th>Dept</th><th>Registered Year</th><th>Present</th><th>Late</th><th>Half day</th><th>Leave</th><th>Absent</th><th>%</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.StudentCode}>
                  <td>{r.StudentCode}</td><td><strong>{r.StudentName}</strong></td><td>{r.DepartmentName}</td><td>{r.RegisteredYear}</td>
                  <td>{r.Present}</td><td>{r.Late}</td><td>{r.HalfDay}</td><td>{r.Leave}</td><td>{r.Absent}</td>
                  <td className={pctClass(r.Percentage)}>{r.Percentage != null ? `${r.Percentage}%` : "—"}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={10} style={{ color: "var(--text-muted)" }}>No students match.</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
