import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Flash, NumField, Segmented, SectionHead, SwitchRow } from "../components/ConfigUi";
import { EmployeeSelect, useEmployees } from "../components/EmployeeSelect";
import { Icons } from "../components/SidebarIcons";

type Mode = "every" | "from" | "only";

const ord = (n: number) => {
  const v = n % 100;
  if (v >= 11 && v <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
};

const penalises = (mode: Mode, n: number, k: number) => (mode === "from" ? k >= n : mode === "only" ? k === n : k % n === 0);

const MODE_OPTIONS: [string, string][] = [["every", "Every Nth late day"], ["from", "Nth and every later one"], ["only", "Only the Nth"]];
const DIR_OPTIONS: [string, string][] = [["alternate", "1st punch IN, 2nd OUT, 3rd IN …"], ["device", "As sent by the device"]];

const pad = (n: number) => String(n).padStart(2, "0");

const STEPS: { title: string; text: string; to?: string; link?: string }[] = [
  { title: "Leave", text: "A day on fully approved leave is Leave (HOD / Manager, then Principal / Director). If it falls on a weekly off or holiday, the leave type decides whether that day counts.", to: "/ess/leave-approvals", link: "Leave Approvals" },
  { title: "Holiday", text: "A holiday is an Off day.", to: "/config/holidays", link: "Holidays" },
  { title: "Weekly off", text: "The employee's category sets the weekly off days. With no punches the day is Weekly off.", to: "/config/categories", link: "Categories" },
  { title: "No punch", text: "No punches on a working day is Absent." },
  { title: "Hours worked", text: "Under the category's absent limit is Absent. Under its half-day limit is a Half day.", to: "/config/categories", link: "Categories" },
  { title: "Late or early by a lot", text: "Arriving or leaving later or earlier than the category's minutes makes the day a Half day.", to: "/config/categories", link: "Categories" },
  { title: "Late-count rule", text: "The rule on this page: the Nth late day in a month becomes a Half day." },
  { title: "Absent on both sides", text: "A weekly off or holiday between absences can become Absent, if the category turns that on.", to: "/config/categories", link: "Categories" },
];

export function AttendanceRulesPage() {
  const employees = useEmployees();

  const [enabled, setEnabled] = useState(true);
  const [days, setDays] = useState(3);
  const [mode, setMode] = useState<Mode>("every");
  const [saved, setSaved] = useState<{ enabled: boolean; days: number; mode: Mode } | null>(null);
  // Punch handling
  const [dupSeconds, setDupSeconds] = useState(60);
  const [dirMode, setDirMode] = useState<"alternate" | "device">("alternate");
  const [savedPunch, setSavedPunch] = useState<{ dupSeconds: number; dirMode: string } | null>(null);
  const [repairFrom, setRepairFrom] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`; });
  const [repairing, setRepairing] = useState(false);
  const [repairStatus, setRepairStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [saving, setSaving] = useState(false);

  // Check an employee
  const now = new Date();
  const [empCode, setEmpCode] = useState("");
  const [month, setMonth] = useState(`${now.getFullYear()}-${pad(now.getMonth() + 1)}`);
  const [review, setReview] = useState<any>(null);
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState("");

  // Recalculate
  const [recalcMonth, setRecalcMonth] = useState(`${now.getFullYear()}-${pad(now.getMonth() + 1)}`);
  const [recalcing, setRecalcing] = useState(false);
  const [recalcStatus, setRecalcStatus] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    api.getAttendanceRules()
      .then((r: any) => {
        const l = r.late_rule;
        setEnabled(!!l.enabled); setDays(l.days); setMode(l.mode);
        setSaved({ enabled: !!l.enabled, days: l.days, mode: l.mode });
        const pr = r.punch_rule;
        if (pr) { setDupSeconds(pr.duplicate_seconds); setDirMode(pr.direction_mode); setSavedPunch({ dupSeconds: pr.duplicate_seconds, dirMode: pr.direction_mode }); }
      })
      .catch((e) => setStatus({ text: e?.message || "Could not load the rules.", ok: false }));
  }, []);

  const dirty = !saved || saved.enabled !== enabled || saved.days !== days || saved.mode !== mode
    || !savedPunch || savedPunch.dupSeconds !== dupSeconds || savedPunch.dirMode !== dirMode;

  const strip = useMemo(() => Array.from({ length: 12 }, (_, i) => i + 1), []);
  const sentence = useMemo(() => {
    if (!enabled) return "The late-count rule is off. Late days are still shown in reports but never change the day's status.";
    const firstFew = strip.filter((k) => penalises(mode, days, k)).slice(0, 3).map(ord);
    if (mode === "every") return `Every ${ord(days)} late day in a month becomes a Half day: the ${firstFew.join(", ")}${days * 3 <= 12 ? "…" : ""} late day.`;
    if (mode === "from") return `From the ${ord(days)} late day in a month, that day and every later late day becomes a Half day.`;
    return `Only the ${ord(days)} late day in a month becomes a Half day. Later late days stay Present.`;
  }, [enabled, days, mode, strip]);

  const save = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const r: any = await api.updateAttendanceRules({ enabled, days, mode, duplicate_seconds: dupSeconds, direction_mode: dirMode });
      setSaved({ enabled, days, mode });
      setSavedPunch({ dupSeconds, dirMode });
      setStatus({ text: `Saved. This month was recalculated for ${r.recalculated?.employees ?? 0} employee(s).`, ok: true });
    } catch (e: any) {
      setStatus({ text: e?.message || "Could not save.", ok: false });
    } finally {
      setSaving(false);
    }
  };

  const runReview = async () => {
    if (!empCode) { setReviewError("Choose an employee first."); return; }
    setReviewing(true); setReviewError(""); setReview(null);
    try {
      const [y, m] = month.split("-").map(Number);
      setReview(await api.getLateReview({ employee_code: empCode, year: y, month: m }));
    } catch (e: any) {
      setReviewError(e?.message || "Could not check this employee.");
    } finally {
      setReviewing(false);
    }
  };

  const recalc = async () => {
    const [y, m] = recalcMonth.split("-").map(Number);
    const last = new Date(y, m, 0).getDate();
    if (!window.confirm(`Recalculate attendance for every employee for ${recalcMonth}?`)) return;
    setRecalcing(true); setRecalcStatus(null);
    try {
      const r: any = await api.recalculateAttendance({ from_date: `${y}-${pad(m)}-01`, to_date: `${y}-${pad(m)}-${pad(last)}` });
      setRecalcStatus({ text: `Recalculated ${r.rows_written} day-records for ${r.employees} employee(s).`, ok: true });
    } catch (e: any) {
      setRecalcStatus({ text: e?.message || "Recalculation failed.", ok: false });
    } finally {
      setRecalcing(false);
    }
  };

  const empName = employees.find((e) => String(e.EmployeeCode) === empCode)?.EmployeeName;

  const repair = async () => {
    if (!window.confirm(`Apply the punch rule to stored punches from ${repairFrom}? Repeated reads inside the duplicate window are deleted and IN/OUT is renumbered, then attendance is recalculated.`)) return;
    setRepairing(true); setRepairStatus(null);
    try {
      const r: any = await api.repairPunches({ from_date: repairFrom });
      setRepairStatus({ text: `${r.punches} punches checked: ${r.duplicates_deleted} duplicates removed, ${r.directions_changed} IN/OUT corrected, attendance recalculated for ${r.recalculated?.employees ?? 0} employee(s).`, ok: true });
    } catch (e: any) {
      setRepairStatus({ text: e?.message || "Repair failed.", ok: false });
    } finally {
      setRepairing(false);
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Attendance Rules</h2>
          <p className="sub">How punches become Present, Half day, Absent or Leave. One set of rules for every employee. Shift timings and grace stay in Shifts.</p>
        </div>
        <Link to="/config/shifts" className="btn btn-outline-reports">Go to Shifts</Link>
      </div>

      <Flash status={status} />

      {/* Late-count rule */}
      <section className="section-card">
        <SectionHead icon={Icons.logs} title="Late arrivals" desc="Turn repeated late days into a half day" />
        <div className="switch-list" style={{ marginTop: 0, paddingTop: 0, borderTop: 0 }}>
          <SwitchRow id="lr-on" checked={enabled} onChange={setEnabled} title="Use the late-count rule"
            desc="Counts the days an employee arrives late in a calendar month and turns some of them into a half day." />
        </div>

        <div className={"lr-body" + (enabled ? "" : " is-off")}>
          <div className="hours-row" style={{ marginTop: 18 }}>
            <div>
              <label className="field-label" htmlFor="lr-days">Late days (N)</label>
              <NumField id="lr-days" max={31} suffix="days" disabled={!enabled} value={days} onChange={(v) => setDays(Math.max(1, v))} />
            </div>
            <div>
              <span className="field-label">Which late days</span>
              <Segmented label="Which late days" value={mode} onChange={(v) => setMode(v as Mode)} options={MODE_OPTIONS} />
            </div>
          </div>

          <div className="lr-strip" role="img" aria-label="Which late days become half days">
            {strip.map((k) => {
              const hit = enabled && penalises(mode, days, k);
              return (
                <span key={k} className={"lr-box" + (hit ? " is-hit" : "")}>
                  <b>{ord(k)}</b>
                  <em>{hit ? "½ day" : "Present"}</em>
                </span>
              );
            })}
          </div>
        </div>

        <p className="lr-sentence">{sentence}</p>
        <ul className="lr-notes">
          <li><strong>Late</strong> is decided by the IN punch alone: the first punch is after the shift start plus its grace time. A day with a missing OUT punch still counts as a late day. Grace comes from the shift (Grace time), or the category if the shift has none.</li>
          <li>Days on leave, holidays, weekly offs and absences never count as late days.</li>
          <li>The count restarts on the 1st of every month, and always counts from the 1st even when only part of a month is recalculated.</li>
          <li>A day that is already a half day (for example, too few hours worked) keeps its status but still counts as a late day.</li>
        </ul>

        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", marginTop: 18 }}>
          <button type="button" className="btn btn-primary-purple" onClick={save} disabled={saving || !dirty}>{saving ? "Saving…" : "Save rule"}</button>
          {!dirty && saved && <span className="sd-sub">Saved</span>}
          {dirty && saved && <span className="sd-sub">You have unsaved changes. Saving also recalculates this month.</span>}
        </div>
      </section>

      {/* Punch handling */}
      <section className="section-card">
        <SectionHead icon={Icons.devices} title="Punch handling" desc="Repeated reads and IN / OUT direction" />
        <div className="hours-row" style={{ marginTop: 18 }}>
          <div>
            <label className="field-label" htmlFor="pr-dup">Duplicate punch window</label>
            <NumField id="pr-dup" max={3600} suffix="seconds" value={dupSeconds} onChange={(v) => setDupSeconds(Math.max(0, v))} />
          </div>
          <div>
            <span className="field-label">Direction of each punch</span>
            <Segmented label="Direction of each punch" value={dirMode} onChange={(v) => setDirMode(v as "alternate" | "device")} options={DIR_OPTIONS} />
          </div>
        </div>
        <ul className="lr-notes">
          <li>A face reader keeps re-reading a face that stays in front of it and sends the same punch several times within seconds. Punches of one employee closer together than the window count as <strong>one</strong> punch (the first is kept). 60 seconds suits most sites; 0 turns this off.</li>
          <li>With <strong>1st IN, 2nd OUT</strong> the punches of each day are numbered in time order, so devices that report no direction ("INOUT") still show a proper IN and OUT. Hours are always worked out from the first and last punch of the day (Categories → "Use only the first and last punch").</li>
          <li>New punches follow these settings immediately. Use <strong>Repair stored punches</strong> once to clean up punches recorded before the rule was set.</li>
        </ul>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", marginTop: 12 }}>
          <div>
            <label className="field-label" htmlFor="pr-from">Repair from</label>
            <input id="pr-from" type="date" value={repairFrom} onChange={(e) => e.target.value && setRepairFrom(e.target.value)} />
          </div>
          <button type="button" className="btn btn-outline-reports" onClick={repair} disabled={repairing || dirty} title={dirty ? "Save the rule first" : ""}>{repairing ? "Repairing…" : "Repair stored punches"}</button>
          {dirty && <span className="sd-sub">Save the rule first (button above).</span>}
        </div>
        <Flash status={repairStatus} />
      </section>

      {/* Check an employee */}
      <section className="section-card">
        <SectionHead icon={Icons.employees} title="Check an employee" desc="See exactly which late days became half days" />
        <div className="hours-row" style={{ marginBottom: 0 }}>
          <div style={{ flex: "1 1 280px", minWidth: 0 }}>
            <label className="field-label" htmlFor="lr-emp">Employee</label>
            <EmployeeSelect id="lr-emp" employees={employees} value={empCode} onChange={setEmpCode} style={{ width: "100%" }} />
          </div>
          <div>
            <label className="field-label" htmlFor="lr-month">Month</label>
            <input id="lr-month" type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
          </div>
          <button type="button" className="btn btn-outline-reports" onClick={runReview} disabled={reviewing || !empCode}>{reviewing ? "Checking…" : "Check"}</button>
        </div>
        {reviewError && <p className="note-err">{reviewError}</p>}

        {review && (
          <div style={{ marginTop: 20 }}>
            <div className="cfg-stats" style={{ marginBottom: 14 }}>
              <span className="cfg-stat"><b>{review.late_days.length}</b><span>Late days</span></span>
              <span className="cfg-stat"><b style={{ color: "#8f4300" }}>{review.penalised_days}</b><span>Made half days</span></span>
              <span className="cfg-stat"><b>{review.totals.P}</b><span>Present</span></span>
              <span className="cfg-stat"><b>{review.totals.H}</b><span>Half days</span></span>
              <span className="cfg-stat"><b>{review.totals.A}</b><span>Absent</span></span>
              <span className="cfg-stat"><b>{review.totals.L}</b><span>Leave</span></span>
            </div>
            {review.late_days.length === 0 ? (
              <div className="cfg-empty" style={{ padding: "22px 12px" }}><strong>No late days</strong><span>{empName || empCode} was never late in this month.</span></div>
            ) : (
              <div className="tf-users" style={{ maxHeight: "none" }}>
                <table className="table cfg-table">
                  <thead><tr><th>Late day</th><th>Date</th><th>First punch</th><th>Late by</th><th>Result</th></tr></thead>
                  <tbody>
                    {review.late_days.map((d: any) => (
                      <tr key={d.date} className={d.penalised ? "is-picked" : ""}>
                        <td><b>{ord(d.number)}</b></td>
                        <td>{d.weekday}, {d.date}</td>
                        <td className="cfg-time">{d.first_in || "—"}</td>
                        <td>{d.late_minutes} min</td>
                        <td>{d.penalised ? <span className="badge badge-amber">Half day (late rule)</span> : d.status === "H" ? <span className="badge badge-amber">Half day</span> : <span className="badge badge-green">Present</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Recalculate */}
      <section className="section-card">
        <SectionHead icon={Icons.calendar} title="Recalculate attendance" desc="Apply the current rules to a month that was already processed" />
        <div className="hours-row" style={{ marginBottom: 0 }}>
          <div>
            <label className="field-label" htmlFor="rc-month">Month</label>
            <input id="rc-month" type="month" value={recalcMonth} onChange={(e) => e.target.value && setRecalcMonth(e.target.value)} />
          </div>
          <button type="button" className="btn btn-outline-reports" onClick={recalc} disabled={recalcing}>{recalcing ? "Recalculating…" : "Recalculate all employees"}</button>
        </div>
        <Flash status={recalcStatus} />
        <p className="sd-sub" style={{ marginTop: 10 }}>Reports and registers also recalculate the month whenever you open them, so this is only needed to refresh the dashboard and stored data.</p>
      </section>

      {/* How it is calculated */}
      <section className="section-card">
        <SectionHead icon={Icons.document} title="How a day is calculated" desc="Rules are applied in this order. The first that fits decides the day." />
        <ol className="lr-steps">
          {STEPS.map((s) => (
            <li key={s.title}>
              <div><strong>{s.title}</strong><span>{s.text}</span></div>
              {s.to && <Link to={s.to} className="notif-link">{s.link} →</Link>}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
