import { useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import { EmployeeSearch } from "../../components/EmployeeSelect";
import { Req } from "../../components/Req";
import { DeptYearFilter, toNum, todayIso, useDepartments } from "./common";

const STATUSES = ["Present", "Late", "HalfDay", "Absent", "Leave", "WeeklyOff"];
const LABEL: Record<string, string> = { HalfDay: "Half Day", WeeklyOff: "Weekly Off" };
const label = (s: string) => LABEL[s] || s;

/** Calendar days from..to inclusive (0 when backwards or incomplete). */
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

const BLANK_MANUAL = { StudentCode: "", FromDate: todayIso(), ToDate: todayIso(), Status: "Present", InTime: "", OutTime: "" };

export function StudentAttendancePage() {
  const departments = useDepartments();
  const [date, setDate] = useState(todayIso());
  const [deptFilter, setDeptFilter] = useState("");
  const [regYearFilter, setRegYearFilter] = useState("");
  const [data, setData] = useState<any>({ total: 0, counts: {}, rows: [] });
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [loading, setLoading] = useState(false);
  const [students, setStudents] = useState<any[]>([]);
  const [manual, setManual] = useState(BLANK_MANUAL);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkStatus, setBulkStatus] = useState("Present");

  const load = () => {
    setLoading(true);
    api.getStudentDaily({ date, department_id: toNum(deptFilter), registered_year: regYearFilter || undefined })
      .then(setData).catch((e) => setMsg({ text: e.message, ok: false })).finally(() => setLoading(false));
  };
  useEffect(load, [date, deptFilter, regYearFilter]);
  useEffect(() => { setSelected(new Set()); }, [date, deptFilter, regYearFilter]);
  useEffect(() => {
    api.getStudents({ department_id: toNum(deptFilter), registered_year: regYearFilter || undefined }).then(setStudents).catch(() => setStudents([]));
  }, [deptFilter, regYearFilter]);

  // Students in the shape the type-to-search picker expects (search by name, register no. or roll no.).
  const studentChoices = useMemo(() => {
    const deptName = new Map(departments.map((d: any) => [d.DepartmentId, d.DepartmentName]));
    return students.map((s) => ({
      EmployeeId: s.StudentId ?? s.StudentCode, EmployeeCode: s.StudentCode, EmployeeName: s.StudentName,
      ShortNo: s.RollNo, Department: deptName.get(s.DepartmentId),
    }));
  }, [students, departments]);

  const mark = async (code: string, status: string) => {
    setMsg(null);
    if (!status) { await api.clearStudentManual(code, date).catch((e) => setMsg({ text: e.message, ok: false })); load(); return; }
    try { await api.markStudentAttendance({ StudentCode: code, AttendanceDate: date, Status: status }); load(); }
    catch (e: any) { setMsg({ text: e.message, ok: false }); }
  };

  const days = spanDays(manual.FromDate, manual.ToDate);
  const saveManual = async () => {
    setMsg(null); setSaving(true);
    try {
      const r: any = await api.markStudentAttendanceBulk({
        StudentCodes: [manual.StudentCode], FromDate: manual.FromDate, ToDate: manual.ToDate, Status: manual.Status,
        InTime: manual.InTime || null, OutTime: manual.OutTime || null,
      });
      const who = studentChoices.find((s) => s.EmployeeCode === manual.StudentCode)?.EmployeeName || manual.StudentCode;
      setMsg({ text: `${who} marked ${label(manual.Status)} for ${r.days} day${r.days === 1 ? "" : "s"} (${manual.FromDate} to ${manual.ToDate}).`, ok: true });
      load();
    } catch (e: any) {
      setMsg({ text: e.message || "Failed to save.", ok: false });
    } finally { setSaving(false); }
  };

  const allCodes: string[] = data.rows.map((r: any) => r.StudentCode);
  const allTicked = allCodes.length > 0 && allCodes.every((c) => selected.has(c));
  const toggle = (code: string) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(code)) next.delete(code); else next.add(code);
    return next;
  });
  const markSelected = async () => {
    setMsg(null);
    try {
      await api.markStudentAttendanceBulk({ StudentCodes: Array.from(selected), FromDate: date, ToDate: date, Status: bulkStatus });
      setMsg({ text: `${selected.size} student${selected.size === 1 ? "" : "s"} marked ${label(bulkStatus)} on ${date}.`, ok: true });
      setSelected(new Set());
      load();
    } catch (e: any) { setMsg({ text: e.message || "Failed to mark.", ok: false }); }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Student Attendance</h2>
          <p className="sub">Daily attendance from face/device punches, by department and registered year. Mark attendance by hand where needed: manual entries (✎) are kept until reset to auto.</p>
        </div>
      </div>
      {msg && <p className={msg.ok ? "note-ok" : "note-err"}>{msg.text}</p>}

      <div className="section-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Manual Attendance</h3>
        <p style={{ margin: "0 0 12px", color: "var(--text-muted)", fontSize: 13.5 }}>
          For one student over one or more days, e.g. when the reader was down or the student forgot to punch.
        </p>
        <div className="form-row-2">
          <label><span>Student <Req /></span>
            <EmployeeSearch employees={studentChoices} value={manual.StudentCode} placeholder="Type student name, register or roll no…"
              onChange={(c) => setManual({ ...manual, StudentCode: c })} />
          </label>
          <label><span>Status <Req /></span>
            <select value={manual.Status} onChange={(e) => setManual({ ...manual, Status: e.target.value })}>
              {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
            </select>
          </label>
          <label><span>From <Req /></span><input type="date" value={manual.FromDate} max={todayIso()}
            onChange={(e) => setManual({ ...manual, FromDate: e.target.value, ToDate: manual.ToDate < e.target.value ? e.target.value : manual.ToDate })} /></label>
          <label><span>To <Req /></span><input type="date" value={manual.ToDate} min={manual.FromDate} max={todayIso()}
            onChange={(e) => setManual({ ...manual, ToDate: e.target.value })} /></label>
          <label>In time (optional)<input type="time" value={manual.InTime} onChange={(e) => setManual({ ...manual, InTime: e.target.value })} /></label>
          <label>Out time (optional)<input type="time" value={manual.OutTime} onChange={(e) => setManual({ ...manual, OutTime: e.target.value })} /></label>
        </div>
        <div style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Quick:</span>
          {[1, 2, 3].map((n) => {
            const to = addDays(manual.FromDate, n - 1);
            return (
              <button key={n} type="button" className="btn-device-ghost" disabled={to > todayIso()}
                onClick={() => setManual({ ...manual, ToDate: to })}>
                {n} day{n > 1 ? "s" : ""}
              </button>
            );
          })}
          <strong style={{ marginLeft: 6 }}>{days ? `${days} day${days === 1 ? "" : "s"}: ${manual.FromDate} to ${manual.ToDate}` : "Pick valid dates"}</strong>
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-primary-purple" onClick={saveManual} disabled={saving || !manual.StudentCode || !days}>
            {saving ? "Saving…" : "Save attendance"}
          </button>
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
          {STATUSES.map((s) => `${label(s)} ${data.counts?.[s] ?? 0}`).join(" · ")}
        </p>
        {selected.size > 0 && (
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", margin: "0 0 12px", padding: "8px 12px",
            background: "var(--primary-soft)", borderRadius: "var(--radius)" }}>
            <strong>{selected.size} selected</strong>
            <span>mark as</span>
            <select value={bulkStatus} onChange={(e) => setBulkStatus(e.target.value)} aria-label="Status for selected students">
              {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
            </select>
            <span>on {date}</span>
            <button className="btn btn-primary-purple" onClick={markSelected}>Mark selected</button>
            <button className="btn-device-ghost" onClick={() => setSelected(new Set())}>Clear</button>
          </div>
        )}
        <table className="table table-compact">
          <thead><tr>
            <th><input type="checkbox" aria-label="Select all students" checked={allTicked}
              onChange={() => setSelected(allTicked ? new Set() : new Set(allCodes))} /></th>
            <th>Code</th><th>Name</th><th>Dept</th><th>Registered Year</th><th>Status</th><th>In</th><th>Out</th><th>Late (min)</th><th>Override</th>
          </tr></thead>
          <tbody>
            {data.rows.map((r: any) => (
              <tr key={r.StudentCode}>
                <td><input type="checkbox" aria-label={`Select ${r.StudentName}`} checked={selected.has(r.StudentCode)} onChange={() => toggle(r.StudentCode)} /></td>
                <td>{r.StudentCode}</td>
                <td><strong>{r.StudentName}</strong></td>
                <td>{r.DepartmentName}</td>
                <td>{r.RegisteredYear}</td>
                <td>{r.Status ? label(r.Status) : ""}{r.LeaveCode ? ` (${r.LeaveCode})` : ""}{r.Source === "Manual" ? " ✎" : ""}</td>
                <td>{r.InTime}</td>
                <td>{r.OutTime}</td>
                <td>{r.LateMinutes || ""}</td>
                <td>
                  <select value="" onChange={(e) => mark(r.StudentCode, e.target.value === "__auto" ? "" : e.target.value)}>
                    <option value="">Mark…</option>
                    {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
                    {r.Source === "Manual" && <option value="__auto">Reset to auto</option>}
                  </select>
                </td>
              </tr>
            ))}
            {!loading && data.rows.length === 0 && <tr><td colSpan={10} style={{ color: "var(--text-muted)" }}>No students match the filter.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
