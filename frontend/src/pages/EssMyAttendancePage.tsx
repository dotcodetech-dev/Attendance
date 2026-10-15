import { FormEvent, useMemo, useState } from "react";

import { api } from "../api/client";
import { EmployeeSelect, useEmployees } from "../components/EmployeeSelect";
import { Flash } from "../components/ConfigUi";
import { Req } from "../components/Req";

type AttendanceDay = {
  AttendanceDate: string;
  DayNumber: number;
  DayLabel: string;
  Status: string;
  StatusLabel: string;
  ShiftName?: string | null;
  ShiftTime?: string | null;
  FirstIn?: string | null;
  LastOut?: string | null;
  TotalLogs: number;
  ActualWorkMinutes: number;
  Remarks?: string | null;
};

type AttendanceSummary = {
  EmployeeCode: string;
  EmployeeName?: string | null;
  Department?: string | null;
  Year: number;
  Month: number;
  MonthLabel: string;
  PresentDays: number;
  AbsentDays: number;
  LeaveDays: number;
  OffDays: number;
  days: AttendanceDay[];
};

const WEEK = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Status code -> look. Colour is never the only cue: each day also shows its code.
const LOOK: Record<string, { bg: string; fg: string; label: string }> = {
  P: { bg: "#e4f6ec", fg: "#0d6b3a", label: "Present" },
  A: { bg: "#fdecec", fg: "#9b1c25", label: "Absent" },
  L: { bg: "#efe9ff", fg: "#4a25c9", label: "Leave" },
};
const lookOf = (code: string) => LOOK[code] ?? { bg: "#eef0f7", fg: "#4d5473", label: "Off / holiday" };

const hm = (mins: number) => {
  const h = Math.floor(mins / 60), m = mins % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
};

const pad = (n: number) => String(n).padStart(2, "0");

export function EssMyAttendancePage() {
  const employees = useEmployees();
  const [employeeCode, setEmployeeCode] = useState("");
  const [month, setMonth] = useState(pad(new Date().getMonth() + 1));
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [summary, setSummary] = useState<AttendanceSummary | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [recalcing, setRecalcing] = useState(false);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);
  const [downloading, setDownloading] = useState(false);

  const selectedDay = useMemo(
    () => summary?.days.find((item) => item.AttendanceDate === selectedDate) ?? summary?.days[0],
    [summary, selectedDate]
  );

  const load = async () => {
    try {
      setLoading(true);
      setError("");
      const data = await api.getEmployeeAttendanceSummary({
        employee_code: employeeCode.trim(),
        year: Number(year),
        month: Number(month),
      });
      setSummary(data);
      setSelectedDate(data.days[0]?.AttendanceDate ?? null);
    } catch (err: any) {
      setSummary(null);
      setError(err?.message || "Failed to load attendance.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    load();
  };

  const range = () => {
    const y = Number(year), m = Number(month);
    return { from_date: `${y}-${pad(m)}-01`, to_date: `${y}-${pad(m)}-${pad(new Date(y, m, 0).getDate())}`, employee_code: employeeCode.trim() || undefined };
  };

  const recalculate = async () => {
    setRecalcing(true);
    setNote(null);
    try {
      const res = await api.recalculateAttendance(range());
      setNote({ text: `Recalculated ${res.rows_written} day-records across ${res.employees} employee(s).`, ok: true });
      if (summary) await load();
    } catch (err: any) {
      setNote({ text: err?.message || "Recalculation failed.", ok: false });
    } finally {
      setRecalcing(false);
    }
  };

  const downloadCsv = async () => {
    setDownloading(true);
    setNote(null);
    try {
      await api.downloadAttendanceCsv(range());
    } catch (err: any) {
      setNote({ text: err?.message || "CSV download failed.", ok: false });
    } finally {
      setDownloading(false);
    }
  };

  // Blank cells so day 1 lands under its real weekday.
  const lead = summary?.days.length ? new Date(summary.days[0].AttendanceDate.slice(0, 10) + "T00:00:00").getDay() : 0;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>My Attendance</h2>
          <p className="sub">A month at a glance for one employee: present, absent, leave and days off, with the detail for any day.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="section-card ess-filter">
        <div className="hours-row" style={{ marginBottom: 0 }}>
          <div style={{ flex: "1 1 280px", minWidth: 0 }}>
            <label className="field-label" htmlFor="at-emp">Employee <Req /></label>
            <EmployeeSelect id="at-emp" employees={employees} value={employeeCode} onChange={setEmployeeCode} required style={{ width: "100%" }} />
          </div>
          <div>
            <label className="field-label" htmlFor="at-month">Month</label>
            <input id="at-month" type="month" value={`${year}-${month}`}
              onChange={(e) => { const [y, m] = e.target.value.split("-"); if (y && m) { setYear(y); setMonth(m); } }} />
          </div>
          <button type="submit" className="btn btn-primary-purple" disabled={loading || !employeeCode}>{loading ? "Loading…" : "Show attendance"}</button>
          <button type="button" className="btn btn-outline-reports" onClick={recalculate} disabled={recalcing}
            title="Recompute stored daily attendance for this month from raw punches. Leave the employee empty to recalculate everyone.">
            {recalcing ? "Recalculating…" : "Recalculate month"}
          </button>
          <button type="button" className="btn btn-outline-reports" onClick={downloadCsv} disabled={downloading}
            title="Download the computed daily attendance for this month as a CSV file.">
            {downloading ? "Preparing…" : "Download CSV"}
          </button>
        </div>
      </form>

      <Flash status={note} />
      {error && <p className="note-err" style={{ marginTop: 0 }}>{error}</p>}

      {summary ? (
        <>
          <div className="sd-kpis" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))", marginBottom: 20 }}>
            <div className="sd-kpi">
              <div className="sd-kpi-top"><span>Employee</span></div>
              <div className="sd-kpi-val" style={{ fontSize: 20 }}>{summary.EmployeeName || summary.EmployeeCode}</div>
              <div className="sd-kpi-note">{summary.MonthLabel}{summary.Department ? ` · ${summary.Department}` : ""}</div>
            </div>
            <div className="sd-kpi"><div className="sd-kpi-top"><i style={{ background: "#1aa45b" }} /><span>Present</span></div><div className="sd-kpi-val">{summary.PresentDays}</div><div className="sd-kpi-note">days</div></div>
            <div className="sd-kpi"><div className="sd-kpi-top"><i style={{ background: "#dc4c5b" }} /><span>Absent</span></div><div className="sd-kpi-val">{summary.AbsentDays}</div><div className="sd-kpi-note">days</div></div>
            <div className="sd-kpi"><div className="sd-kpi-top"><i style={{ background: "#8b6cf5" }} /><span>Leave / off</span></div><div className="sd-kpi-val">{summary.LeaveDays} <small style={{ fontSize: 16, color: "#737a96" }}>/ {summary.OffDays}</small></div><div className="sd-kpi-note">leave days / days off</div></div>
          </div>

          <div className="ess-split">
            <div className="section-card" style={{ marginBottom: 0 }}>
              <div className="cal-head">{WEEK.map((d) => <span key={d}>{d}</span>)}</div>
              <div className="cal-grid">
                {Array.from({ length: lead }).map((_, i) => <span key={"b" + i} />)}
                {summary.days.map((day) => {
                  const look = lookOf(day.Status);
                  const sel = selectedDay?.AttendanceDate === day.AttendanceDate;
                  return (
                    <button key={day.AttendanceDate} type="button" className={"cal-day" + (sel ? " on" : "")}
                      style={{ background: look.bg, color: look.fg }} onClick={() => setSelectedDate(day.AttendanceDate)}
                      aria-label={`${day.DayNumber} ${summary.MonthLabel}: ${day.StatusLabel}`} aria-pressed={sel}>
                      <b>{day.DayNumber}</b>
                      <span>{day.Status}</span>
                    </button>
                  );
                })}
              </div>
              <div className="sd-key" style={{ marginTop: 16 }}>
                {Object.entries(LOOK).map(([k, v]) => <span key={k}><i style={{ background: v.bg, border: `1px solid ${v.fg}` }} />{k} = {v.label}</span>)}
                <span><i style={{ background: "#eef0f7", border: "1px solid #4d5473" }} />Other = off / holiday</span>
              </div>
            </div>

            <div className="section-card" style={{ marginBottom: 0 }}>
              <p className="section-eyebrow">Day details</p>
              {selectedDay ? (
                <>
                  <h3 style={{ margin: "0 0 4px", fontSize: 20 }}>{pad(selectedDay.DayNumber)} {summary.MonthLabel}</h3>
                  <span className="badge" style={{ background: lookOf(selectedDay.Status).bg, color: lookOf(selectedDay.Status).fg }}>{selectedDay.StatusLabel}</span>
                  <dl className="shift-stats" style={{ marginTop: 16, borderTop: 0, paddingTop: 0 }}>
                    <div><dt>First in</dt><dd>{selectedDay.FirstIn || "—"}</dd></div>
                    <div><dt>Last out</dt><dd>{selectedDay.LastOut || "—"}</dd></div>
                    <div><dt>Time worked</dt><dd>{selectedDay.ActualWorkMinutes ? hm(selectedDay.ActualWorkMinutes) : "—"}</dd></div>
                    <div><dt>Punches</dt><dd>{selectedDay.TotalLogs}</dd></div>
                    <div><dt>Shift</dt><dd>{selectedDay.ShiftName || "—"}</dd></div>
                    <div><dt>Shift time</dt><dd>{selectedDay.ShiftTime || "—"}</dd></div>
                  </dl>
                  {selectedDay.Remarks && <p className="ess-remark">{selectedDay.Remarks}</p>}
                </>
              ) : <p style={{ margin: 0, color: "var(--text-muted)" }}>No attendance details available.</p>}
            </div>
          </div>
        </>
      ) : (
        <div className="section-card cfg-empty">
          <strong>Choose an employee and a month</strong>
          <span>Then select Show attendance. If a month looks empty, there are no punches recorded for that employee yet.</span>
        </div>
      )}
    </div>
  );
}
