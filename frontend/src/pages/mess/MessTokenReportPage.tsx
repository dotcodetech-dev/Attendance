import { useEffect, useState } from "react";

import { api } from "../../api/client";
import { formatIST } from "../../utils/datetime";

const today = new Date().toISOString().slice(0, 10);

export function MessTokenReportPage() {
  const [date, setDate] = useState(today);
  const [meal, setMeal] = useState("");
  const [employee, setEmployee] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setRows(await api.getMessTokens({ date: date || undefined, meal: meal || undefined, employee_code: employee.trim() || undefined }));
    } catch { setRows([]); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const fmt = (iso?: string) => (iso ? formatIST(iso) : "-");

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Mess Token Report</h2>
          <p className="sub">All issued tokens with meal, number, date/time, print status and reprint history.</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="field field-sm"><label>Date</label><input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
        <div className="field"><label>Meal</label>
          <select value={meal} onChange={(e) => setMeal(e.target.value)}>
            <option value="">All</option><option>Breakfast</option><option>Lunch</option><option>Dinner</option>
          </select>
        </div>
        <div className="field"><label>Employee</label><input value={employee} placeholder="All" onChange={(e) => setEmployee(e.target.value)} /></div>
        <div className="toolbar-actions">
          <button className="btn btn-primary-purple" onClick={load} disabled={loading}>{loading ? "…" : "View"}</button>
        </div>
      </div>

      <div className="section-card">
        <div className="table-scroll">
          <table className="table table-compact">
            <thead>
              <tr><th>Token</th><th>Employee</th><th>Meal</th><th>Date</th><th>Issued At</th><th>Status</th><th>Reprints</th><th>Last Reprint</th></tr>
            </thead>
            <tbody>
              {!loading && rows.length === 0 ? (
                <tr><td colSpan={8} style={{ color: "var(--text-muted)" }}>No tokens for this filter.</td></tr>
              ) : null}
              {rows.map((t) => (
                <tr key={t.MessTokenId}>
                  <td><strong>{t.TokenLabel}</strong></td>
                  <td>{t.EmployeeCode} · {t.EmployeeName || "-"}</td>
                  <td><span className="badge badge-purple">{t.MealType}</span></td>
                  <td>{t.TokenDate}</td>
                  <td>{fmt(t.CreatedAt)}</td>
                  <td><span className="badge badge-green">{t.PrintStatus}</span></td>
                  <td className="num">{t.ReprintCount}</td>
                  <td>{t.LastReprintAt ? fmt(t.LastReprintAt) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
