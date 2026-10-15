import { api } from "../../api/client";
import { IdCells, IdHead } from "./grouped";
import { RangeReportPage } from "./RangeReportPage";

const stack = { whiteSpace: "pre-line" as const, fontWeight: 600 };

/** Attendance Report with Time & Leave: the time grid plus dynamic leave-code
 *  totals and A / WO / P / Total / Late Hrs / Late Cl summary columns. */
export function MusterLeavePage() {
  return (
    <RangeReportPage
      reportKey="muster-leave"
      musterPrint="leave"
      title="Attendance Report (Time & Leave)"
      description="Daily In / Out / worked-hours muster with per-employee leave totals for the range."
      getFn={api.getMusterLeave}
      minWidth={1200}
      subtitle={(d) => `From ${d.FromLabel} To ${d.ToLabel}   ·   Category : ${d.Category}`}
      colSpan={(d) => 6 + d.DateHeaders.length + d.Columns.length}
      head={(d) => (
        <tr>
          <IdHead sticky />
          {d.DateHeaders.map((h: string, i: number) => <th key={i} className="num">{h}</th>)}
          {d.Columns.map((c: string) => <th key={c} className="num">{c}</th>)}
          <th className="num">Total</th><th className="num">Late Hrs</th><th className="num">Late Cl</th>
        </tr>
      )}
      row={(d) => (e: any) => (
        <tr key={e.FaceId ?? e.EmployeeCode}>
          <IdCells e={e} sticky />
          {e.days.map((v: string, i: number) => <td key={i} className="num" style={stack}>{v}</td>)}
          {d.Columns.map((c: string) => <td key={c} className="num"><strong>{e.Counts?.[c] ?? 0}</strong></td>)}
          <td className="num"><strong>{e.Total}</strong></td>
          <td className="num">{e.LateHrs}</td>
          <td className="num">{e.LateCl}</td>
        </tr>
      )}
    />
  );
}
