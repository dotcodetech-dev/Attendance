import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { ReportFilters, emptyFilters, filterQuery } from "../../components/ReportFilters";
import { GroupedBody, IdCells, IdHead, printReport, withCategory } from "./grouped";

export function LeaveBalanceReportPage() {
  const [year, setYear] = useState(new Date().getFullYear());
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

  const load = async () => {
    setLoading(true); setError("");
    try {
      setData(await api.getLeaveBalanceReport({ year, ...filterQuery(filters, false) }));
    } catch (e: any) { setData(null); setError(e?.message || "Failed to load report."); }
    finally { setLoading(false); }
  };

  const download = async (fmt: "xlsx" | "pdf") => {
    setBusy(fmt);
    try { await api.downloadReport("leave-balance", fmt, { year, grouped, ...filterQuery(filters, false) }); }
    catch (e: any) { setError(e?.message || "Download failed."); }
    finally { setBusy(""); }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Leave Balance Report</h2>
          <p className="sub">Per employee: entitlement, taken and remaining balance for each leave type.</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="field field-sm"><label>Year</label>
          <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} /></div>
        <ReportFilters value={filters} onChange={setFilters} withDateRange={false} />
        <label className="field-check"><input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.target.checked)} /> Group by department</label>
        <div className="toolbar-actions">
          <button className="btn btn-primary-purple" onClick={load} disabled={loading}>{loading ? "Loading…" : "View Report"}</button>
          <button className="btn btn-outline-reports" onClick={() => download("xlsx")} disabled={!data || !!busy}>{busy === "xlsx" ? "…" : "Excel"}</button>
          <button className="btn btn-outline-reports" onClick={() => download("pdf")} disabled={!data || !!busy}>{busy === "pdf" ? "…" : "PDF"}</button>
          <button className="btn btn-outline-reports" onClick={() => printReport("Leave Balance Report", withCategory("Year " + (data?.Year || year), data), tableRef.current, orgName)} disabled={!data}>Print</button>
        </div>
      </div>

      {error && <p className="note-err">{error}</p>}

      {data && (
        <div className="section-card">
          <div className="table-scroll">
          <table className="table table-compact" ref={tableRef}>
            <thead>
              <tr>
                <IdHead />
                {data.LeaveTypes.map((t: any) => (
                  <th key={t.Code} colSpan={3} style={{ textAlign: "center" }}>{t.Code}</th>
                ))}
              </tr>
              <tr>
                <th colSpan={3}></th>
                {data.LeaveTypes.map((t: any) => (
                  <>
                    <th key={`${t.Code}-e`} style={{ textAlign: "center" }}>Ent</th>
                    <th key={`${t.Code}-t`} style={{ textAlign: "center" }}>Taken</th>
                    <th key={`${t.Code}-b`} style={{ textAlign: "center" }}>Bal</th>
                  </>
                ))}
              </tr>
            </thead>
            {grouped ? (
              <GroupedBody groups={data.groups} colSpan={3 + 3 * data.LeaveTypes.length} renderRow={renderRow} />
            ) : (
            <tbody>
              {data.employees.map((e: any, i: number) => renderRow({ ...e, SNo: i + 1 }))}
            </tbody>
            )}
          </table>
          </div>
        </div>
      )}
      {!data && !loading && !error && <div className="empty-state">Choose a year and click <strong>View Report</strong>.</div>}
    </div>
  );

  function renderRow(e: any) {
                const byCode: Record<string, any> = {};
                e.balances.forEach((b: any) => { byCode[b.Code] = b; });
                return (
                  <tr key={e.FaceId ?? e.EmployeeCode}>
                    <IdCells e={e} />
                    {data.LeaveTypes.map((t: any) => {
                      const b = byCode[t.Code] || { Entitled: 0, Taken: 0, Balance: 0 };
                      return (
                        <>
                          <td key={`${t.Code}-e`} style={{ textAlign: "center" }}>{b.Entitled}</td>
                          <td key={`${t.Code}-t`} style={{ textAlign: "center" }}>{b.Taken}</td>
                          <td key={`${t.Code}-b`} style={{ textAlign: "center", fontWeight: 700 }}>{b.Balance}</td>
                        </>
                      );
                    })}
                  </tr>
                );
  }
}
