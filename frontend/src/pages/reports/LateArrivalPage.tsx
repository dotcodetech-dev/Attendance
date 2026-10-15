import { api } from "../../api/client";
import { IdCells, IdHead } from "./grouped";
import { RangeReportPage } from "./RangeReportPage";

/** Late Arrival Report: one row per employee-day arriving after the grace window. */
export function LateArrivalPage() {
  return (
    <RangeReportPage
      reportKey="late-arrival"
      title="Late Arrival Report"
      description="Days an employee punched in later than the shift grace window, within the range."
      getFn={api.getLateArrival}
      minWidth={760}
      subtitle={(d) => `From ${d.FromLabel} To ${d.ToLabel}   ·   Category : ${d.Category}`}
      colSpan={() => 7}
      head={() => (
        <tr>
          <IdHead /><th>Date</th><th>Shift</th>
          <th className="num">Actual In</th><th className="num">Late Hrs</th>
        </tr>
      )}
      row={() => (e: any) => (
        <tr key={`${e.FaceId ?? e.EmployeeCode}-${e.Date}`}>
          <IdCells e={e} />
          <td>{e.Date}</td>
          <td>{e.ShiftTime}</td>
          <td className="num">{e.FirstIn}</td>
          <td className="num" style={{ color: "#b45309", fontWeight: 600 }}>{e.Minutes}</td>
        </tr>
      )}
    />
  );
}
