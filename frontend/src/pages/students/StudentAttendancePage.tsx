import { useEffect, useState } from "react";

import { api } from "../../api/client";
import { DeptYearFilter, toNum, todayIso, useDepartments } from "./common";

const STATUSES = ["Present", "Late", "HalfDay", "Absent", "Leave", "WeeklyOff"];

export function StudentAttendancePage() {
  const departments = useDepartments();
  const [date, setDate] = useState(todayIso());
  const [deptFilter, setDeptFilter] = useState("");
  const [regYearFilter, setRegYearFilter] = useState("");
  const [data, setData] = useState<any>({ total: 0, counts: {}, rows: [] });
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true); setMsg("");
    api.getStudentDaily({ date, department_id: toNum(deptFilter), registered_year: regYearFilter || undefined })
      .then(setData).catch((e) => setMsg(e.message)).finally(() => setLoading(false));
  };
  useEffect(load, [date, deptFilter, regYearFilter]);

  const mark = async (code: string, status: string) => {
    if (!status) { await api.clearStudentManual(code, date).catch((e) => setMsg(e.message)); load(); return; }
    try { await api.markStudentAttendance({ StudentCode: code, AttendanceDate: date, Status: status }); load(); }
    catch (e: any) { setMsg(e.message); }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Student Attendance</h2>
          <p className="sub">Daily attendance from face/device punches, by department and registered year.</p>
        </div>
      </div>
      <div className="section-card">
        <div className="form-row-2" style={{ marginBottom: 12 }}>
          <label>Date<input type="date" value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} /></label>
          <DeptYearFilter departments={departments} departmentId={deptFilter} registeredYear={regYearFilter}
            onDepartment={setDeptFilter} onRegisteredYear={setRegYearFilter} />
        </div>
        <p style={{ margin: "0 0 12px" }}>
          <strong>{data.total}</strong> students ·{" "}
          {STATUSES.map((s) => `${s} ${data.counts?.[s] ?? 0}`).join(" · ")}
        </p>
        {msg && <p className="note-err">{msg}</p>}
        <table className="table table-compact">
          <thead><tr><th>Code</th><th>Name</th><th>Dept</th><th>Registered Year</th><th>Status</th><th>In</th><th>Out</th><th>Late (min)</th><th>Override</th></tr></thead>
          <tbody>
            {data.rows.map((r: any) => (
              <tr key={r.StudentCode}>
                <td>{r.StudentCode}</td>
                <td><strong>{r.StudentName}</strong></td>
                <td>{r.DepartmentName}</td>
                <td>{r.RegisteredYear}</td>
                <td>{r.Status}{r.LeaveCode ? ` (${r.LeaveCode})` : ""}{r.Source === "Manual" ? " ✎" : ""}</td>
                <td>{r.InTime}</td>
                <td>{r.OutTime}</td>
                <td>{r.LateMinutes || ""}</td>
                <td>
                  <select value="" onChange={(e) => mark(r.StudentCode, e.target.value === "__auto" ? "" : e.target.value)}>
                    <option value="">Mark…</option>
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    {r.Source === "Manual" && <option value="__auto">Reset to auto</option>}
                  </select>
                </td>
              </tr>
            ))}
            {!loading && data.rows.length === 0 && <tr><td colSpan={9} style={{ color: "var(--text-muted)" }}>No students match the filter.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
