import { useState } from "react";

import { api } from "../../api/client";

const now = new Date();

export function IndividualSheetPage() {
  const [employeeCode, setEmployeeCode] = useState("");
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    if (!employeeCode.trim()) { setError("Enter an employee code."); return; }
    setLoading(true); setError("");
    try {
      setData(await api.getIndividualSheet({ employee_code: employeeCode.trim(), year, month }));
    } catch (e: any) { setData(null); setError(e?.message || "Failed to load report."); }
    finally { setLoading(false); }
  };

  const download = async (fmt: "csv" | "pdf") => {
    setBusy(fmt);
    try { await api.downloadReport("individual", fmt, { employee_code: employeeCode.trim(), year, month }); }
    catch (e: any) { setError(e?.message || "Download failed."); }
    finally { setBusy(""); }
  };

  const tone = (s: string) => s === "A" ? "#fdecea" : s === "P" ? "#e8f5e9" : s === "W" ? "#eef2ff" : s === "O" ? "#fff7e6" : s === "L" ? "#f3e8ff" : "#fff";

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Individual Attendance Sheet</h2>
          <p className="sub">One employee's full month: in/out, status, late/early and remarks.</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="field"><label>Employee Code</label>
          <input value={employeeCode} placeholder="e.g. CSC26018 (or the Face ID)" onChange={(e) => setEmployeeCode(e.target.value)} /></div>
        <div className="field field-sm"><label>Year</label>
          <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} /></div>
        <div className="field"><label>Month</label>
          <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>{new Date(2000, m - 1, 1).toLocaleString("en", { month: "long" })}</option>
            ))}
          </select>
        </div>
        <div className="toolbar-actions">
          <button className="btn btn-primary-purple" onClick={load} disabled={loading}>{loading ? "Loading…" : "View Sheet"}</button>
          <button className="btn btn-outline-reports" onClick={() => download("csv")} disabled={!data || !!busy}>{busy === "csv" ? "…" : "CSV"}</button>
          <button className="btn btn-outline-reports" onClick={() => download("pdf")} disabled={!data || !!busy}>{busy === "pdf" ? "…" : "PDF"}</button>
        </div>
      </div>

      {error && <p className="note-err">{error}</p>}

      {data && (
        <div className="section-card">
          <h3>{data.EmployeeName || data.EmployeeCode} — {data.MonthLabel}</h3>
          <div className="table-scroll">
          <table className="table table-compact">
            <thead>
              <tr><th>Date</th><th>Day</th><th>Status</th><th>Category</th><th>In</th><th>Out</th><th>Late</th><th>Early</th><th>Remarks</th></tr>
            </thead>
            <tbody>
              {data.days.map((d: any) => (
                <tr key={d.Date} style={{ background: tone(d.Status) }}>
                  <td>{d.Date}</td><td>{d.DayLabel}</td>
                  <td>{d.StatusLabel}{d.LeaveCode ? ` (${d.LeaveCode})` : ""}</td>
                  <td>{d.CategoryName || "-"}</td>
                  <td>{d.FirstIn || "-"}</td><td>{d.LastOut || "-"}</td>
                  <td style={{ textAlign: "center" }}>{d.Late || 0}</td>
                  <td style={{ textAlign: "center" }}>{d.Early || 0}</td>
                  <td>{d.Remarks || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
      {!data && !loading && !error && <div className="empty-state">Enter an employee code and click <strong>View Sheet</strong>.</div>}
    </div>
  );
}
