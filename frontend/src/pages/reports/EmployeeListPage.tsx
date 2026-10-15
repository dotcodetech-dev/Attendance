import { api } from "../../api/client";
import { IdCells, IdHead } from "./grouped";
import { RangeReportPage } from "./RangeReportPage";

/** Employee List: master list of staff, grouped by department. No date range. */
export function EmployeeListPage() {
  return (
    <RangeReportPage
      reportKey="employee-list"
      title="Employee List"
      description="Master list of employees with type, category and status."
      getFn={api.getEmployeeList}
      withDateRange={false}
      minWidth={1000}
      subtitle={(d) => `${d.Count} employees   ·   Category : ${d.Category}   ·   as on ${d.GeneratedLabel}`}
      colSpan={() => 9}
      head={() => (
        <tr>
          <IdHead /><th>Department</th><th>Designation</th>
          <th>Type</th><th>Category</th><th>Status</th><th>Joining Date</th>
        </tr>
      )}
      row={() => (e: any) => (
        <tr key={e.FaceId ?? e.EmployeeCode}>
          <IdCells e={e} />
          <td>{e.Department}</td>
          <td>{e.Designation}</td>
          <td>{e.Type}</td>
          <td>{e.CategoryName}</td>
          <td>{e.Status}</td>
          <td>{e.JoiningDate}</td>
        </tr>
      )}
    />
  );
}
