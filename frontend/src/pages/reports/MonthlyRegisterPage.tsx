import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { ReportFilters, emptyFilters, filterQuery } from "../../components/ReportFilters";
import { GroupedBody, IdCells, IdHead, printReport, withCategory } from "./grouped";

const now = new Date();
const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

export function MonthlyRegisterPage() {
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [filters, setFilters] = useState(emptyFilters());
  const [grouped, setGrouped] = useState(true);
  const [orgName, setOrgName] = useState("");
  const tableRef = useRef<HTMLTableElement>(null);
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.getOrganization().then((o: any) => setOrgName(o?.OrgName || "")).catch(() => {});
  }, []);

  const load = async (recalculate = false) => {
    setLoading(true);
    setError("");
    try {
      // refresh=true reprocesses raw punches against current shift/category
      // rules before reading; plain view reuses the materialized table.
      setData(await api.getMonthlyRegister({
        year, month, refresh: recalculate, ...filterQuery(filters, false),
      }));
    } catch (e: any) {
      setData(null);
      setError(e?.message || "Failed to load report.");
    } finally {
      setLoading(false);
    }
  };

  const download = async (fmt: "xlsx" | "pdf") => {
    setBusy(fmt);
    try {
      await api.downloadReport("register", fmt, {
        year, month, grouped, ...filterQuery(filters, false),
      });
    } catch (e: any) {
      setError(e?.message || "Download failed.");
    } finally {
      setBusy("");
    }
  };

  const days = data ? Array.from({ length: data.DaysInMonth }, (_, i) => i + 1) : [];
  const cellColor = (v: string) =>
    v === "A" ? "#fdecea" : v === "P" ? "#e8f5e9" : v === "PL" ? "#fff3cd" : v === "H" ? "#ffe9c7" : v === "HL" ? "#ffd9a8" : v === "WO" ? "#eef2ff" : v === "H*" ? "#fff7e6" : v === "-" ? "#f8fafc" : "#f3e8ff";

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Monthly Attendance Register</h2>
          <p className="sub">
            Muster grid of all employees by day, with monthly totals.
            &nbsp;<span className="badge badge-green">P</span> Present
            &nbsp;<span className="badge badge-amber">PL</span> Present (Late)
            &nbsp;<span className="badge badge-amber">H</span> Half day
            &nbsp;<span className="badge badge-amber">HL</span> Half day (late rule)
            &nbsp;<span className="badge badge-red">A</span> Absent
            &nbsp;<span className="badge badge-blue">WO</span> Weekly-off
            &nbsp;<span className="badge badge-amber">H*</span> Holiday
            &nbsp;<span className="badge badge-purple">CL</span> Leave
          </p>
        </div>
      </div>

      <div className="toolbar">
        <div className="field field-sm"><label>Year</label>
          <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} /></div>
        <div className="field"><label>Month</label>
          <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
            {MONTHS.map((m) => <option key={m} value={m}>{new Date(2000, m - 1, 1).toLocaleString("en", { month: "long" })}</option>)}
          </select>
        </div>
        <ReportFilters value={filters} onChange={setFilters} withDateRange={false} />
        <label className="field-check"><input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.target.checked)} /> Group by department</label>
        <div className="toolbar-actions">
          <button className="btn btn-primary-purple" onClick={() => load(false)} disabled={loading}>{loading ? "Loading…" : "View Report"}</button>
          <button className="btn btn-outline-reports" onClick={() => load(true)} disabled={loading} title="Reprocess punches with current shift, weekly-off and grace rules">
            {loading ? "…" : "Recalculate"}
          </button>
          <button className="btn btn-outline-reports" onClick={() => download("xlsx")} disabled={!data || !!busy}>{busy === "xlsx" ? "…" : "Excel"}</button>
          <button className="btn btn-outline-reports" onClick={() => download("pdf")} disabled={!data || !!busy}>{busy === "pdf" ? "…" : "PDF"}</button>
          <button className="btn btn-outline-reports" onClick={() => printReport("Monthly Attendance Register", withCategory(data?.MonthLabel || "", data), tableRef.current, orgName)} disabled={!data}>Print</button>
        </div>
      </div>

      {error && <p className="note-err">{error}</p>}

      {data && (
        <div className="section-card">
          <h3>{data.MonthLabel} <span className="badge badge-gray">{data.employees.length} employees</span></h3>
          <div className="table-scroll">
            <table className="table table-compact table-sticky" style={{ minWidth: 900 }} ref={tableRef}>
              <thead>
                <tr>
                  <IdHead sticky />
                  {days.map((d) => <th key={d} className="num">{d}</th>)}
                  <th className="num">P</th><th className="num">A</th><th className="num">H</th><th className="num">WO</th><th className="num">H*</th><th className="num" title="Days arrived late (beyond grace), including days the late rule made a half day">Late</th>
                  {data.LeaveCodes.map((c: string) => <th key={c} className="num">{c}</th>)}
                </tr>
              </thead>
              {grouped ? (
                <GroupedBody groups={data.groups} colSpan={9 + days.length + data.LeaveCodes.length} renderRow={renderRow} />
              ) : (
              <tbody>
                {data.employees.map((e: any, i: number) => renderRow({ ...e, SNo: i + 1 }))}
              </tbody>
              )}
            </table>
          </div>
        </div>
      )}
      {!data && !loading && !error && <div className="empty-state">Choose a month and click <strong>View Report</strong>.</div>}
    </div>
  );

  function renderRow(e: any) {
    return (
                  <tr key={e.FaceId ?? e.EmployeeCode}>
                    <IdCells e={e} sticky />
                    {e.days.map((v: string, i: number) => (
                      <td key={i} className="num" style={{ background: cellColor(v), fontWeight: 600 }}>{v}</td>
                    ))}
                    <td className="num">{e.PresentDays}</td>
                    <td className="num">{e.AbsentDays}</td>
                    <td className="num">{e.HalfDays}</td>
                    <td className="num">{e.WeeklyOffDays}</td>
                    <td className="num">{e.HolidayDays}</td>
                    <td className="num" style={{ color: (e.LateDays || 0) > 0 ? "#b45309" : undefined, fontWeight: 600 }}>{e.LateDays || 0}</td>
                    {data.LeaveCodes.map((c: string) => <td key={c} className="num">{e.LeaveByCode[c] || 0}</td>)}
                  </tr>
    );
  }
}
