import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { ReportFilters, emptyFilters, filterQuery } from "../../components/ReportFilters";
import { GroupedBody, IdCells, IdHead, printReport, withCategory } from "./grouped";

type Kind = "all" | "present" | "absent" | "leave";

const KINDS: { value: Kind; label: string }[] = [
  { value: "present", label: "Present" },
  { value: "absent", label: "Absent" },
  { value: "leave", label: "On Leave" },
  { value: "all", label: "All" },
];

const today = new Date().toISOString().slice(0, 10);

export function DailyAttendancePage() {
  const [date, setDate] = useState(today);
  const [kind, setKind] = useState<Kind>("present");
  const [filters, setFilters] = useState(emptyFilters());
  const [orgName, setOrgName] = useState("");
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const tableRef = useRef<HTMLTableElement>(null);

  useEffect(() => {
    api.getOrganization().then((o: any) => setOrgName(o?.OrgName || "")).catch(() => {});
  }, []);

  const params = () => ({ date, kind, ...filterQuery(filters, false) });

  const load = async (refresh = false) => {
    setLoading(true); setError("");
    try { setData(await api.getDailyReport({ ...params(), refresh: refresh || undefined })); }
    catch (e: any) { setData(null); setError(e?.message || "Failed to load report."); }
    finally { setLoading(false); }
  };

  const download = async (fmt: "xlsx" | "pdf") => {
    setBusy(fmt);
    try { await api.downloadReport("daily", fmt, { ...params(), grouped: true }); }
    catch (e: any) { setError(e?.message || "Download failed."); }
    finally { setBusy(""); }
  };

  const title = KINDS.find((k) => k.value === kind)?.label + (kind === "all" ? " Employees" : " List");
  const statusBadge = (e: any) => {
    const late = e.Bucket === "present" && (e.LateMinutes || 0) > 0;
    const cls = late ? "badge-amber" : e.Bucket === "present" ? "badge-green" : e.Bucket === "absent" ? "badge-red" : e.Bucket === "leave" ? "badge-purple" : "badge-blue";
    return <span className={`badge ${cls}`}>{e.StatusLabel}</span>;
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Present / Absent Report</h2>
          <p className="sub">Who was present, absent or on leave on a given day — grouped by department. Today's list is live: any punch counts as present; an IN after the shift start (plus grace) shows as <span className="badge badge-amber">Late</span>.</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="field field-sm"><label>Date</label>
          <input type="date" value={date} max={today} onChange={(e) => setDate(e.target.value)} /></div>
        <div className="field"><label>Show</label>
          <select value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </select>
        </div>
        <ReportFilters value={filters} onChange={setFilters} withDateRange={false} />
        <div className="toolbar-actions">
          <button className="btn btn-primary-purple" onClick={() => load(false)} disabled={loading}>{loading ? "Loading…" : "View Report"}</button>
          <button className="btn btn-outline-reports" onClick={() => load(true)} disabled={loading} title="Reprocess this day's punches first">Recalculate</button>
          <button className="btn btn-outline-reports" onClick={() => download("xlsx")} disabled={!data || !!busy}>{busy === "xlsx" ? "…" : "Excel"}</button>
          <button className="btn btn-outline-reports" onClick={() => download("pdf")} disabled={!data || !!busy}>{busy === "pdf" ? "…" : "PDF"}</button>
          <button className="btn btn-outline-reports" onClick={() => printReport(title, withCategory(data?.DayLabel || "", data), tableRef.current, orgName)} disabled={!data}>Print</button>
        </div>
      </div>

      {error && <p className="note-err">{error}</p>}

      {data && (
        <div className="section-card">
          <h3>
            {title} — {data.DayLabel}
            &nbsp;<span className="badge badge-green">Present {data.Totals.present}</span>
            &nbsp;<span className="badge badge-amber">Late {data.Totals.late || 0}</span>
            &nbsp;<span className="badge badge-red">Absent {data.Totals.absent}</span>
            &nbsp;<span className="badge badge-purple">Leave {data.Totals.leave}</span>
            &nbsp;<span className="badge badge-blue">Off {data.Totals.off}</span>
            &nbsp;<span className="badge badge-gray">Total {data.Totals.total}</span>
          </h3>
          {data.employees.length === 0 ? (
            <div className="empty-state">No employees match for this day.</div>
          ) : (
            <div className="table-scroll">
              <table className="table table-compact" ref={tableRef}>
                <thead>
                  <tr>
                    <IdHead /><th>Status</th><th>Shift</th>
                    <th className="num">In</th><th className="num">Out</th><th className="num">Late (min)</th><th>Remarks</th>
                  </tr>
                </thead>
                <GroupedBody groups={data.groups} colSpan={9} renderRow={(e: any) => (
                  <tr key={e.FaceId ?? e.EmployeeCode}>
                    <IdCells e={e} />
                    <td>{statusBadge(e)}</td>
                    <td>{e.ShiftName || ""}</td>
                    <td className="num">{e.FirstIn || "—"}</td>
                    <td className="num">{e.LastOut || "—"}</td>
                    <td className="num" style={{ color: (e.LateMinutes || 0) > 0 ? "#b45309" : undefined }}>{e.LateMinutes || 0}</td>
                    <td style={{ color: "#667", fontSize: 12 }}>{e.Remarks || ""}</td>
                  </tr>
                )} />
              </table>
            </div>
          )}
        </div>
      )}
      {!data && !loading && !error && <div className="empty-state">Choose a date and click <strong>View Report</strong>.</div>}
    </div>
  );
}
