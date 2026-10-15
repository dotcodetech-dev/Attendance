import { api } from "../../api/client";
import { IdCells, IdHead } from "./grouped";
import { RangeReportPage } from "./RangeReportPage";

/** In-Out List: every raw punch per employee per day for the range. */
export function InOutListPage() {
  return (
    <RangeReportPage
      reportKey="in-out"
      title="In-Out List"
      description="All device punches per employee per day for the selected range, grouped by department. Employees with no punches in the range are listed too."
      getFn={api.getInOutList}
      minWidth={760}
      subtitle={(d) => `From ${d.FromLabel} To ${d.ToLabel}   ·   Category : ${d.Category}`}
      colSpan={() => 6}
      head={() => (
        <tr>
          <IdHead /><th>Date</th><th className="num">Punches</th><th>Times (In / Out)</th>
        </tr>
      )}
      row={() => (e: any) => (
        <tr key={`${e.FaceId ?? e.EmployeeCode}-${e.Date}`}>
          <IdCells e={e} />
          <td>{e.Date}</td>
          <td className="num">{e.Count}</td>
          <td>{e.Punches}</td>
        </tr>
      )}
    />
  );
}
