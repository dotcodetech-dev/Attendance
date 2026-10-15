import { useState } from "react";

import { api } from "../../api/client";
import { ReportFilters, emptyFilters, filterQuery } from "../../components/ReportFilters";
import { IdCells, IdHead, withCategory } from "./grouped";

const now = new Date();

export function LateOtReportPage() {
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [filters, setFilters] = useState(emptyFilters());
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true); setError("");
    try {
      setData(await api.getLateOtReport({ year, month, ...filterQuery(filters, false) }));
    } catch (e: any) { setData(null); setError(e?.message || "Failed to load report."); }
    finally { setLoading(false); }
  };

  const download = async (fmt: "csv" | "pdf") => {
    setBusy(fmt);
    try { await api.downloadReport("late-ot", fmt, { year, month, ...filterQuery(filters, false) }); }
    catch (e: any) { setError(e?.message || "Download failed."); }
    finally { setBusy(""); }
  };

  const hm = (m: number) => `${Math.floor(m / 60)}h ${m % 60}m`;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Late / Early Report</h2>
          <p className="sub">Monthly late-coming and early-going totals per employee.</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="field field-sm"><label>Year</label>
          <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} /></div>
        <div className="field"><label>Month</label>
          <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>{new Date(2000, m - 1, 1).toLocaleString("en", { month: "long" })}</option>
            ))}
          </select>
        </div>
        <ReportFilters value={filters} onChange={setFilters} withDateRange={false} />
        <div className="toolbar-actions">
          <button className="btn btn-primary-purple" onClick={load} disabled={loading}>{loading ? "Loading…" : "View Report"}</button>
          <button className="btn btn-outline-reports" onClick={() => download("csv")} disabled={!data || !!busy}>{busy === "csv" ? "…" : "CSV"}</button>
          <button className="btn btn-outline-reports" onClick={() => download("pdf")} disabled={!data || !!busy}>{busy === "pdf" ? "…" : "PDF"}</button>
        </div>
      </div>

      {error && <p className="note-err">{error}</p>}

      {data && (
        <div className="section-card">
          <h3>{withCategory(data.MonthLabel, data)}</h3>
          <div className="table-scroll">
          <table className="table table-compact">
            <thead>
              <tr><IdHead /><th>Department</th><th>Late Days</th><th>Total Late</th><th>Total Early</th></tr>
            </thead>
            <tbody>
              {data.employees.map((e: any) => (
                <tr key={e.FaceId ?? e.EmployeeCode}>
                  <IdCells e={e} />
                  <td>{e.Department || "-"}</td>
                  <td style={{ textAlign: "center" }}>{e.LateDays}</td>
                  <td style={{ textAlign: "center" }}>{hm(e.TotalLateMinutes)}</td>
                  <td style={{ textAlign: "center" }}>{hm(e.TotalEarlyMinutes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
      {!data && !loading && !error && <div className="empty-state">Choose a month and click <strong>View Report</strong>.</div>}
    </div>
  );
}
