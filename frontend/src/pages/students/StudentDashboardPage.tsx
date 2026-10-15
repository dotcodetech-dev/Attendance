import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { useFeatures } from "../../store/features";
import { toNum, todayIso, useDepartments } from "./common";

// Status colours. Every colour is also labelled with text/numbers, never colour alone.
const C = { present: "#1aa45b", late: "#e8a20c", half: "#8b6cf5", leave: "#3b82f6", absent: "#dc4c5b", off: "#c3c9dc" };

const fmtDay = (iso: string, long = false) =>
  new Date(iso + "T00:00:00").toLocaleDateString(undefined, long
    ? { weekday: "long", day: "numeric", month: "long" }
    : { weekday: "short", day: "numeric", month: "short" });

function useCountUp(target: number, ms = 650) {
  const [val, setVal] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms);
      const v = a + (target - a) * (1 - Math.pow(1 - p, 3));
      setVal(v);
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return val;
}

function Num({ value, decimals = 0, suffix = "" }: { value: number; decimals?: number; suffix?: string }) {
  const v = useCountUp(value);
  return <>{v.toFixed(decimals)}{suffix}</>;
}

/* ---------- Donut: today's status mix ---------- */
function Donut({ k }: { k: any }) {
  const r = 62, circ = 2 * Math.PI * r;
  const parts = [
    { key: "Present", v: k.present, c: C.present },
    { key: "Late", v: k.late, c: C.late },
    { key: "Half day", v: k.half_day, c: C.half },
    { key: "Leave", v: k.leave, c: C.leave },
    { key: "Absent", v: k.absent, c: C.absent },
    { key: "Weekly off", v: k.weekly_off, c: C.off },
  ];
  const total = parts.reduce((a, p) => a + p.v, 0) || 1;
  let offset = 0;
  return (
    <svg viewBox="0 0 160 160" className="sd-donut" role="img"
      aria-label={`Attendance ${k.rate ?? 0} percent. ` + parts.map((p) => `${p.key} ${p.v}`).join(", ")}>
      <circle cx="80" cy="80" r={r} fill="none" stroke="#eef0f7" strokeWidth="16" />
      {parts.filter((p) => p.v > 0).map((p) => {
        const len = (p.v / total) * circ;
        const el = (
          <circle key={p.key} cx="80" cy="80" r={r} fill="none" stroke={p.c} strokeWidth="16"
            strokeDasharray={`${Math.max(len - 2, 0.5)} ${circ}`} strokeDashoffset={-offset}
            transform="rotate(-90 80 80)" style={{ transition: "stroke-dasharray .6s ease" }}>
            <title>{p.key}: {p.v}</title>
          </circle>
        );
        offset += len;
        return el;
      })}
      <text x="80" y="78" textAnchor="middle" className="sd-donut-num">{k.rate == null ? "—" : `${k.rate}%`}</text>
      <text x="80" y="98" textAnchor="middle" className="sd-donut-cap">attendance</text>
    </svg>
  );
}

/* ---------- Trend line/area with hover + click to pick a day ---------- */
function TrendChart({ data, selected, onPick }: { data: any[]; selected: string; onPick: (d: string) => void }) {
  const W = 700, H = 250, L = 40, R = 16, T = 16, B = 32;
  const n = data.length;
  const step = n > 1 ? (W - L - R) / (n - 1) : 0;
  const x = (i: number) => L + i * step;
  const y = (v: number) => T + ((100 - v) * (H - T - B)) / 100;
  const [hover, setHover] = useState<number | null>(null);

  const segs: number[][] = [];
  let cur: number[] = [];
  data.forEach((d, i) => {
    if (d.rate == null) { if (cur.length) segs.push(cur); cur = []; } else cur.push(i);
  });
  if (cur.length) segs.push(cur);
  const line = (s: number[]) => s.map((i, k) => `${k ? "L" : "M"}${x(i)},${y(data[i].rate)}`).join(" ");
  const area = (s: number[]) => `${line(s)} L${x(s[s.length - 1])},${y(0)} L${x(s[0])},${y(0)} Z`;

  const idxAt = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) * W) / r.width;
    return Math.max(0, Math.min(n - 1, Math.round((px - L) / (step || 1))));
  };
  const h = hover != null ? data[hover] : null;
  const selIdx = data.findIndex((d) => d.date === selected);
  const labelEvery = Math.max(1, Math.ceil(n / 7));

  return (
    <div className="sd-trend-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="sd-trend" role="img" aria-label="Daily attendance percentage"
        onMouseMove={(e) => setHover(idxAt(e))} onMouseLeave={() => setHover(null)}
        onClick={(e) => onPick(data[idxAt(e)].date)}>
        <defs>
          <linearGradient id="sdArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5a35e0" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#5a35e0" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {[0, 25, 50, 75, 100].map((g) => (
          <g key={g}>
            <line x1={L} x2={W - R} y1={y(g)} y2={y(g)} stroke="#e3e6f0" strokeDasharray={g === 0 ? "" : "3 4"} />
            <text x={L - 8} y={y(g) + 4} textAnchor="end" className="sd-axis">{g}%</text>
          </g>
        ))}
        {data.map((d, i) => i % labelEvery === 0 || i === n - 1 ? (
          <text key={d.date} x={x(i)} y={H - 8} textAnchor="middle" className="sd-axis">
            {new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })}
          </text>
        ) : null)}
        {segs.map((s, k) => <path key={"a" + k} d={area(s)} fill="url(#sdArea)" />)}
        {segs.map((s, k) => <path key={"l" + k} d={line(s)} fill="none" stroke="#5a35e0" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />)}
        {data.map((d, i) => d.rate == null ? (
          <rect key={"off" + i} x={x(i) - step / 2} y={T} width={Math.max(step, 4)} height={H - T - B} fill="#eef0f7" opacity="0.7" />
        ) : (
          <circle key={"p" + i} cx={x(i)} cy={y(d.rate)} r={i === selIdx ? 6 : 3.5} fill={i === selIdx ? "#5a35e0" : "#fff"}
            stroke="#5a35e0" strokeWidth="2" />
        ))}
        {h && hover != null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="#5a35e0" strokeOpacity=".35" />}
      </svg>
      {h && hover != null && (
        <div className="sd-tip" style={{ left: `${(x(hover) / W) * 100}%` }}>
          <strong>{fmtDay(h.date)}</strong>
          {h.rate == null ? <span>Weekly off / no data</span> : (
            <>
              <span><i style={{ background: C.present }} />Present {h.present}</span>
              <span><i style={{ background: C.absent }} />Absent {h.absent}</span>
              <span><i style={{ background: C.leave }} />Leave {h.leave}</span>
              <span className="sd-tip-rate">{h.rate}%</span>
            </>
          )}
          <em>Click to open this day</em>
        </div>
      )}
    </div>
  );
}

/* ---------- Heatmap colour ---------- */
function heat(rate: number | null) {
  if (rate == null) return { bg: "#f1f3f9", fg: "#737a96" };
  if (rate >= 90) return { bg: "#bfe9d0", fg: "#0b5b31" };
  if (rate >= 80) return { bg: "#d9f0c6", fg: "#3b6412" };
  if (rate >= 70) return { bg: "#fbe8b0", fg: "#7a5200" };
  if (rate >= 60) return { bg: "#f9d0a8", fg: "#8a3f00" };
  return { bg: "#f6c1c6", fg: "#8f1d28" };
}

function Delta({ now, prev }: { now: number | null; prev: number | null }) {
  if (now == null || prev == null) return <span className="sd-delta flat">no earlier day to compare</span>;
  const d = Math.round((now - prev) * 10) / 10;
  if (d === 0) return <span className="sd-delta flat">same as previous day</span>;
  return <span className={"sd-delta " + (d > 0 ? "up" : "down")}>{d > 0 ? "▲" : "▼"} {Math.abs(d)} pts vs previous day</span>;
}

function Kpi({ label, value, of, color, note }: { label: string; value: number; of: number; color: string; note: string }) {
  const pct = of ? Math.round((value / of) * 100) : 0;
  return (
    <div className="sd-kpi">
      <div className="sd-kpi-top"><i style={{ background: color }} /><span>{label}</span></div>
      <div className="sd-kpi-val"><Num value={value} /></div>
      <div className="sd-kpi-bar"><span style={{ width: `${pct}%`, background: color }} /></div>
      <div className="sd-kpi-note">{note}</div>
    </div>
  );
}

export function StudentDashboardPage() {
  const departments = useDepartments();
  const { features } = useFeatures();
  const [date, setDate] = useState(todayIso());
  const [days, setDays] = useState(14);
  const [deptId, setDeptId] = useState("");
  const [year, setYear] = useState("");  // holds a registered-year session label, e.g. "Jan 2026"
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    api.getStudentDashboard({ date, days, department_id: toNum(deptId), registered_year: year || undefined })
      .then((d) => { if (live) { setData(d); setError(""); } })
      .catch((e) => { if (live) setError(e.message || "Could not load the dashboard."); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [date, days, deptId, year]);

  const filtered = !!(deptId || year) || date !== todayIso();
  const reset = () => { setDate(todayIso()); setDeptId(""); setYear(""); };

  if (error && !data) {
    return <div className="section-card"><p className="note-err">{error}</p></div>;
  }
  if (!data) return <div className="section-card"><p style={{ margin: 0 }}>Loading dashboard…</p></div>;

  const k = data.kpis;
  const present = k.present + k.late + k.half_day;
  const empty = k.total === 0;
  const maxArrival = Math.max(1, ...data.arrivals.map((a: any) => a.count));
  const peak = data.arrivals.reduce((b: any, a: any) => (a.count > b.count ? a : b), data.arrivals[0]);
  const lowest = data.by_department.filter((d: any) => d.rate != null).sort((a: any, b: any) => a.rate - b.rate)[0];

  return (
    <div className={"sd-page" + (loading ? " is-loading" : "")}>
      <div className="page-head">
        <div>
          <h2>Student Dashboard</h2>
          <p className="sub">{fmtDay(data.date, true)}. Click any chart to drill into a department, year or day.</p>
        </div>
        <Link to="/students/attendance" className="btn btn-outline-reports">Open daily attendance</Link>
      </div>

      {/* Filters */}
      <div className="sd-filters">
        <label className="sd-f"><span>Date</span>
          <input type="date" value={date} max={todayIso()} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
        <label className="sd-f"><span>Department</span>
          <select value={deptId} onChange={(e) => setDeptId(e.target.value)}>
            <option value="">All departments</option>
            {departments.map((d) => <option key={d.DepartmentId} value={d.DepartmentId}>{d.DepartmentName}</option>)}
          </select>
        </label>
        <label className="sd-f"><span>Registered Year</span>
          <select value={year} onChange={(e) => setYear(e.target.value)}>
            <option value="">All registered years</option>
            {(data.reg_years || []).map((y: string) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <div className="sd-f"><span>Trend</span>
          <div className="seg" role="group" aria-label="Trend length">
            {[7, 14, 30].map((n) => <button key={n} type="button" className={days === n ? "on" : ""} onClick={() => setDays(n)}>{n} days</button>)}
          </div>
        </div>
        {filtered && <button type="button" className="btn-device-ghost sd-reset" onClick={reset}>Reset filters</button>}
      </div>

      {empty ? (
        <div className="section-card sd-empty">
          <h3>No students match these filters</h3>
          <p>{filtered ? "Try resetting the filters." : "Add students to see attendance insights here."}</p>
          {filtered
            ? <button type="button" className="btn btn-primary-purple" onClick={reset}>Reset filters</button>
            : <Link to="/students" className="btn btn-primary-purple">Add students</Link>}
        </div>
      ) : (
        <>
          {/* Hero */}
          <div className="sd-hero">
            <div className="section-card sd-gauge">
              <p className="section-eyebrow">Attendance today</p>
              <div className="sd-gauge-body">
                <Donut k={k} />
                <ul className="sd-legend">
                  {[["Present", k.present, C.present], ["Late", k.late, C.late], ["Half day", k.half_day, C.half],
                    ["Leave", k.leave, C.leave], ["Absent", k.absent, C.absent], ["Weekly off", k.weekly_off, C.off]].map(([l, v, c]: any) => (
                    <li key={l}><i style={{ background: c }} />{l}<b>{v}</b></li>
                  ))}
                </ul>
              </div>
              <Delta now={k.rate} prev={data.prev_rate} />
            </div>
            <div className="sd-kpis">
              <Kpi label="Students" value={k.total} of={k.total} color="#5a35e0" note="Active in this view" />
              <Kpi label="In today" value={present} of={k.total} color={C.present} note={`${k.total ? Math.round((present / k.total) * 100) : 0}% of students`} />
              <Kpi label="Absent" value={k.absent} of={k.total} color={C.absent} note={k.absent ? "Needs follow-up" : "Nobody absent"} />
              <Kpi label="Late arrivals" value={k.late} of={k.total} color={C.late} note="After the grace time" />
              <Kpi label="On leave" value={k.leave} of={k.total} color={C.leave} note="Approved leave" />
              {features.student_leaves && <Link to="/students/leaves" className="sd-kpi sd-kpi-link">
                <div className="sd-kpi-top"><i style={{ background: "#8b6cf5" }} /><span>Pending leave</span></div>
                <div className="sd-kpi-val"><Num value={data.pending_leaves} /></div>
                <div className="sd-kpi-note">{data.pending_leaves ? "Review requests →" : "All caught up"}</div>
              </Link>}
            </div>
          </div>

          {/* Insight strip */}
          <div className="sd-insights">
            {lowest && <div><b>{lowest.name}</b> has the lowest attendance today at <b>{lowest.rate}%</b>.</div>}
            {peak && peak.count > 0 && <div>Most students arrive around <b>{peak.label}</b> ({peak.count} in that half hour).</div>}
            {data.watchlist.length > 0 && <div><b>{data.watchlist.length}</b> student{data.watchlist.length > 1 ? "s" : ""} on the watch-list for the last {data.days} days.</div>}
          </div>

          {/* Trend */}
          <div className="section-card">
            <div className="sd-card-head">
              <div><p className="section-eyebrow">Attendance trend</p><h3>Last {data.days} days</h3></div>
              <span className="sd-hint">Hover for detail, click a day to open it. Shaded columns are weekly offs.</span>
            </div>
            <TrendChart data={data.trend} selected={data.date} onPick={setDate} />
          </div>

          {/* Department + Year */}
          <div className="sd-two">
            <div className="section-card">
              <div className="sd-card-head"><div><p className="section-eyebrow">By department</p><h3>Who is in today</h3></div></div>
              <div className="sd-bars">
                {data.by_department.map((d: any) => {
                  const w = (n: number) => `${d.total ? (n / d.total) * 100 : 0}%`;
                  const on = deptId === String(d.DepartmentId);
                  return (
                    <button key={d.DepartmentId} type="button" className={"sd-bar-row" + (on ? " on" : "")}
                      onClick={() => setDeptId(on ? "" : String(d.DepartmentId))} aria-pressed={on}
                      title={`${d.name}: ${d.present} present, ${d.late} late, ${d.leave} leave, ${d.absent} absent of ${d.total}`}>
                      <span className="sd-bar-name">{d.name}</span>
                      <span className="sd-bar-track">
                        <span style={{ width: w(d.present), background: C.present }} />
                        <span style={{ width: w(d.late), background: C.late }} />
                        <span style={{ width: w(d.half_day), background: C.half }} />
                        <span style={{ width: w(d.leave), background: C.leave }} />
                        <span style={{ width: w(d.absent), background: C.absent }} />
                      </span>
                      <span className="sd-bar-val">{d.rate == null ? "—" : `${d.rate}%`}<small>{d.total}</small></span>
                    </button>
                  );
                })}
              </div>
              <div className="sd-key">
                {[["Present", C.present], ["Late", C.late], ["Half day", C.half], ["Leave", C.leave], ["Absent", C.absent]].map(([l, c]) => (
                  <span key={l}><i style={{ background: c }} />{l}</span>
                ))}
              </div>
            </div>

            <div className="section-card">
              <div className="sd-card-head"><div><p className="section-eyebrow">By registered year</p><h3>Registered year</h3></div></div>
              <div className="sd-years">
                {data.by_year.map((y: any) => {
                  const on = year === String(y.year);
                  const r = y.rate ?? 0;
                  const circ = 2 * Math.PI * 26;
                  return (
                    <button key={y.year} type="button" className={"sd-year" + (on ? " on" : "") + (y.total === 0 ? " none" : "")}
                      onClick={() => y.total > 0 && setYear(on ? "" : String(y.year))} aria-pressed={on} disabled={y.total === 0}>
                      <svg viewBox="0 0 64 64" width="64" height="64" aria-hidden>
                        <circle cx="32" cy="32" r="26" fill="none" stroke="#eef0f7" strokeWidth="7" />
                        <circle cx="32" cy="32" r="26" fill="none" stroke={heat(y.rate).fg === "#737a96" ? "#c3c9dc" : "#5a35e0"} strokeWidth="7"
                          strokeLinecap="round" strokeDasharray={`${(r / 100) * circ} ${circ}`} transform="rotate(-90 32 32)"
                          style={{ transition: "stroke-dasharray .6s ease" }} />
                        <text x="32" y="37" textAnchor="middle" className="sd-year-num">{y.rate == null ? "—" : Math.round(y.rate)}</text>
                      </svg>
                      <span className="sd-year-rate">{y.year}</span>
                      <span className="sd-year-cap">{y.total} students</span>
                      <span className="sd-year-mini">{y.absent} absent · {y.late} late</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Heatmap + arrivals */}
          <div className="sd-two">
            <div className="section-card">
              <div className="sd-card-head">
                <div><p className="section-eyebrow">Heatmap</p><h3>Department × registered year, last {data.days} days</h3></div>
              </div>
              <div className="sd-heat" style={{ gridTemplateColumns: `minmax(110px,1.4fr) repeat(${Math.max(1, (data.reg_years || []).length)}, minmax(56px,1fr))` }}>
                <span />
                {(data.reg_years || []).map((y: string) => <span key={y} className="sd-heat-h">{y}</span>)}
                {data.heatmap.map((row: any) => (
                  <div key={row.DepartmentId} style={{ display: "contents" }}>
                    <span className="sd-heat-name">{row.name}</span>
                    {(data.reg_years || []).map((y: string) => {
                      const cell = row.years[y] || { students: 0, rate: null };
                      const c = heat(cell.rate);
                      return (
                        <button key={y} type="button" className="sd-cell" style={{ background: c.bg, color: c.fg }}
                          disabled={cell.students === 0}
                          title={`${row.name}, ${y}: ${cell.rate ?? "no data"}% (${cell.students} students)`}
                          onClick={() => { setDeptId(String(row.DepartmentId)); setYear(String(y)); }}>
                          {cell.students === 0 ? "·" : cell.rate == null ? "—" : `${Math.round(cell.rate)}%`}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
              <div className="sd-key">
                {[["90%+", "#bfe9d0"], ["80–89", "#d9f0c6"], ["70–79", "#fbe8b0"], ["60–69", "#f9d0a8"], ["Below 60", "#f6c1c6"]].map(([l, c]) => (
                  <span key={l}><i style={{ background: c, border: "1px solid rgba(0,0,0,.08)" }} />{l}</span>
                ))}
              </div>
            </div>

            <div className="section-card">
              <div className="sd-card-head"><div><p className="section-eyebrow">Arrival time</p><h3>When students walk in</h3></div></div>
              <div className="sd-hist" role="img" aria-label="Arrival times in half-hour steps">
                {data.arrivals.map((a: any) => (
                  <div key={a.label} className={"sd-hist-col" + (a === peak && a.count > 0 ? " peak" : "")} title={`${a.label}: ${a.count} students`}>
                    <span className="sd-hist-n">{a.count || ""}</span>
                    <span className="sd-hist-bar" style={{ height: `${(a.count / maxArrival) * 100}%` }} />
                    <span className="sd-hist-l">{a.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Watch-list */}
          <div className="section-card">
            <div className="sd-card-head">
              <div><p className="section-eyebrow">Watch-list</p><h3>Lowest attendance, last {data.days} days</h3></div>
              <span className="sd-hint">Students with at least 3 working days.</span>
            </div>
            {data.watchlist.length === 0 ? (
              <p style={{ margin: 0, color: "var(--text-muted)" }}>Nothing to flag. Attendance looks healthy.</p>
            ) : (
              <table className="table table-compact">
                <thead><tr><th>Student</th><th>Department</th><th>Registered Year</th><th style={{ width: "34%" }}>Attendance</th><th>Absent</th><th>Late</th></tr></thead>
                <tbody>
                  {data.watchlist.map((w: any) => (
                    <tr key={w.StudentCode}>
                      <td><strong>{w.StudentName}</strong><div className="sd-sub">{w.StudentCode}</div></td>
                      <td>{w.DepartmentName}</td>
                      <td>{w.RegisteredYear}</td>
                      <td>
                        <div className="sd-meter"><span style={{ width: `${w.rate}%`, background: w.rate < 60 ? C.absent : w.rate < 75 ? C.late : C.present }} /></div>
                        <b>{w.rate}%</b>
                      </td>
                      <td>{w.absent}</td>
                      <td>{w.late}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
