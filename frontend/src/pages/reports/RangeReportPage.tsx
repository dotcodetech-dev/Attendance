/**
 * Generic page for the staff attendance reports. Supplies the filter bar, the
 * View / Excel / PDF / Print actions and the grouped (by Department)
 * table shell; each report passes its column header, row renderer and group
 * colSpan. Excel/PDF are backend blobs via api.downloadReport; Print is the
 * shared client-side printReport.
 */
import { ReactNode, useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { ReportFilters, ReportFilterValues, emptyFilters, filterQuery } from "../../components/ReportFilters";
import { GroupedBody, printReport, withCategory } from "./grouped";
import { printMuster } from "./musterPrint";

export interface RangeReportConfig {
  reportKey: string;                       // backend /reports/<key>
  title: string;
  description?: ReactNode;
  getFn: (q: Record<string, string | undefined>) => Promise<any>;
  withDateRange?: boolean;                 // false for the Employee List
  head: (data: any) => ReactNode;          // the <tr> of <th> inside <thead>
  colSpan: (data: any) => number;          // group header span
  row: (data: any) => (e: any) => ReactNode;
  subtitle?: (data: any) => string;        // printed/report subtitle
  musterPrint?: "time" | "leave";          // print in the college's muster form (Attendance Time / Time & Leave)
  minWidth?: number;
}

export function RangeReportPage(cfg: RangeReportConfig) {
  const withRange = cfg.withDateRange !== false;
  const [filters, setFilters] = useState<ReportFilterValues>(emptyFilters());
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [orgName, setOrgName] = useState("");
  const [org, setOrg] = useState<any>(null);
  const tableRef = useRef<HTMLTableElement>(null);

  useEffect(() => {
    api.getOrganization().then((o: any) => { setOrgName(o?.OrgName || ""); setOrg(o); }).catch(() => {});
  }, []);

  const query = () => filterQuery(filters, withRange);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setData(await cfg.getFn(query()));
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
      await api.downloadReport(cfg.reportKey, fmt, { ...query(), grouped: true });
    } catch (e: any) {
      setError(e?.message || "Download failed.");
    } finally {
      setBusy("");
    }
  };

  const subtitle = data && cfg.subtitle ? withCategory(cfg.subtitle(data), data) : "";
  const renderRow = data ? cfg.row(data) : () => null;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{cfg.title}</h2>
          {cfg.description && <p className="sub">{cfg.description}</p>}
        </div>
      </div>

      <div className="toolbar">
        <ReportFilters value={filters} onChange={setFilters} withDateRange={withRange} />
        <div className="toolbar-actions">
          <button className="btn btn-primary-purple" onClick={load} disabled={loading}>
            {loading ? "Loading…" : "View Report"}
          </button>
          <button className="btn btn-outline-reports" onClick={() => download("xlsx")} disabled={!data || !!busy}>
            {busy === "xlsx" ? "…" : "Excel"}
          </button>
          <button className="btn btn-outline-reports" onClick={() => download("pdf")} disabled={!data || !!busy}>
            {busy === "pdf" ? "…" : "PDF"}
          </button>
          <button className="btn btn-outline-reports"
                  onClick={() => (cfg.musterPrint ? printMuster(data, org, cfg.musterPrint === "leave") : printReport(cfg.title, subtitle, tableRef.current, orgName))} disabled={!data}>
            Print
          </button>
        </div>
      </div>

      {error && <p className="note-err">{error}</p>}

      {data && (
        <div className="section-card">
          <h3>{subtitle} <span className="badge badge-gray">{data.employees.length} rows</span></h3>
          <div className="table-scroll">
            <table className="table table-compact table-sticky" style={{ minWidth: cfg.minWidth || 900 }} ref={tableRef}>
              <thead>{cfg.head(data)}</thead>
              <GroupedBody groups={data.groups} colSpan={cfg.colSpan(data)} renderRow={renderRow} />
            </table>
          </div>
        </div>
      )}
      {!data && !loading && !error && (
        <div className="empty-state">Set the filters and click <strong>View Report</strong>.</div>
      )}
    </div>
  );
}
