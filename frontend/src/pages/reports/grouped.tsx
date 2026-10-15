/**
 * Shared pieces for department-wise reports.
 *
 * The backend returns `groups: [{Department, Count, employees}]` next to the flat `employees` list. <GroupedBody> renders those as section rows
 * inside any table; the caller supplies the per-employee row.
 */
import React, { Fragment, ReactNode } from "react";

export interface ReportGroup {
  Department: string;
  Count: number;
  employees: any[];
  designations?: { employees: any[] }[]; // older servers still send department -> designation sections
}

export function GroupedBody({ groups, colSpan, renderRow }: {
  groups: ReportGroup[];
  colSpan: number;
  renderRow: (e: any) => ReactNode;
}) {
  return (
    <tbody>
      {groups.map((g) => (
        <Fragment key={g.Department}>
          <tr className="report-group-row">
            <td colSpan={colSpan}>{g.Department} <span className="report-group-count">{g.Count}</span></td>
          </tr>
          {(g.employees ?? g.designations?.flatMap((d) => d.employees) ?? []).map(renderRow)}
        </Fragment>
      ))}
    </tbody>
  );
}

/** The three identity columns every employee report starts with: S.No, Employee Code, Employee Name.
 *  `sticky` pins them while a wide day-grid scrolls sideways. */
const ID_W = [48, 100, 190];
const stickyAt = (i: number, head: boolean): React.CSSProperties => ({
  position: "sticky", left: ID_W.slice(0, i).reduce((a, b) => a + b, 0), minWidth: ID_W[i], maxWidth: ID_W[i],
  background: head ? "var(--surface-muted)" : "#fff", zIndex: head ? 3 : 1,
});
const nowrap: React.CSSProperties = { whiteSpace: "nowrap" };

export function IdHead({ sticky = false }: { sticky?: boolean }) {
  const st = (i: number) => (sticky ? stickyAt(i, true) : undefined);
  return (
    <>
      <th className="num" style={st(0)}>S.No</th>
      <th style={st(1)}>Employee Code</th>
      <th style={st(2)}>Employee Name</th>
    </>
  );
}

export function IdCells({ e, sticky = false }: { e: any; sticky?: boolean }) {
  const st = (i: number) => (sticky ? { ...stickyAt(i, false), ...nowrap } : nowrap);
  return (
    <>
      <td className="num" style={st(0)}>{e.SNo}</td>
      <td style={st(1)}><strong>{e.EmployeeCode}</strong></td>
      <td style={st(2)}>{e.EmployeeName}</td>
    </>
  );
}

/** Append the chosen attendance category (if the report was filtered by one) to a report subtitle. */
export function withCategory(subtitle: string, data: any): string {
  return data?.AttendanceCategory ? `${subtitle}   ·   Attendance Category : ${data.AttendanceCategory}` : subtitle;
}

/** Open the report's table in a print window (A4 landscape, org header). */
export function printReport(title: string, subtitle: string, tableEl: HTMLElement | null, orgName?: string) {
  if (!tableEl) return;
  const w = window.open("", "_blank", "width=1100,height=800");
  if (!w) return;
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>
<style>
  @page { size: A4 landscape; margin: 10mm; }
  body { font: 12px/1.35 Segoe UI, Arial, sans-serif; color: #111; margin: 0; }
  h1 { font-size: 17px; color: #5b21b6; margin: 0 0 2px; }
  .org { font-size: 14px; font-weight: 700; color: #4c1d95; margin-bottom: 2px; }
  .sub { color: #555; margin-bottom: 8px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #cfcfcf; padding: 2px 5px; text-align: left; white-space: nowrap; }
  th { background: #4c1d95; color: #fff; font-size: 11px; }
  td.num, th.num { text-align: center; }
  tr.report-group-row td { background: #5b21b6; color: #fff; font-weight: 700; }
  .report-group-count { font-weight: 400; opacity: .85; margin-left: 6px; }
  .badge { padding: 0 4px; border-radius: 3px; font-size: 11px; }
  tr { page-break-inside: avoid; }
</style></head><body>
${orgName ? `<div class="org">${orgName}</div>` : ""}
<h1>${title}</h1><div class="sub">${subtitle}</div>
${tableEl.outerHTML}
</body></html>`);
  w.document.close();
  w.focus();
  setTimeout(() => { w.print(); }, 250);
}
