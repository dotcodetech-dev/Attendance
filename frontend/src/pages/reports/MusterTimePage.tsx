import { api } from "../../api/client";
import { IdCells, IdHead } from "./grouped";
import { RangeReportPage } from "./RangeReportPage";

const stack = { whiteSpace: "pre-line" as const, fontWeight: 600 };

/** Attendance Report (time only): per-day IN / OUT grid + Late Hrs. */
export function MusterTimePage() {
  return (
    <RangeReportPage
      reportKey="muster-time"
      musterPrint="time"
      title="Attendance Report (Time)"
      description="Daily In / Out muster for the selected range, grouped by department."
      getFn={api.getMusterTime}
      minWidth={1000}
      subtitle={(d) => `From ${d.FromLabel} To ${d.ToLabel}   ·   Category : ${d.Category}`}
      colSpan={(d) => 4 + d.DateHeaders.length}
      head={(d) => (
        <tr>
          <IdHead sticky />
          {d.DateHeaders.map((h: string, i: number) => <th key={i} className="num">{h}</th>)}
          <th className="num">Late Hrs</th>
        </tr>
      )}
      row={() => (e: any) => (
        <tr key={e.FaceId ?? e.EmployeeCode}>
          <IdCells e={e} sticky />
          {e.days.map((v: string, i: number) => <td key={i} className="num" style={stack}>{v}</td>)}
          <td className="num">{e.LateHrs}</td>
        </tr>
      )}
    />
  );
}
