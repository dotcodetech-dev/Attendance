import { api } from "../../api/client";
import { IdCells, IdHead } from "./grouped";
import { RangeReportPage } from "./RangeReportPage";

/** Early Departure Report: one row per employee-day leaving before the shift end grace. */
export function EarlyDeparturePage() {
  return (
    <RangeReportPage
      reportKey="early-departure"
      title="Early Departure Report"
      description="Days an employee punched out earlier than the shift end grace window, within the range."
      getFn={api.getEarlyDeparture}
      minWidth={760}
      subtitle={(d) => `From ${d.FromLabel} To ${d.ToLabel}   ·   Category : ${d.Category}`}
      colSpan={() => 7}
      head={() => (
        <tr>
          <IdHead /><th>Date</th><th>Shift</th>
          <th className="num">Actual Out</th><th className="num">Early Hrs</th>
        </tr>
      )}
      row={() => (e: any) => (
        <tr key={`${e.FaceId ?? e.EmployeeCode}-${e.Date}`}>
          <IdCells e={e} />
          <td>{e.Date}</td>
          <td>{e.ShiftTime}</td>
          <td className="num">{e.LastOut}</td>
          <td className="num" style={{ color: "#b45309", fontWeight: 600 }}>{e.Minutes}</td>
        </tr>
      )}
    />
  );
}
