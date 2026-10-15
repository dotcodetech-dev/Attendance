/**
 * Print for the two college muster reports (Attendance Time / Time & Leave), laid out like the printed form:
 * centred institute heading, yellow column heads, dashed grid, three lines (IN / OUT / worked) per employee,
 * a heading per department with S.No restarting at 1. The PDF and Excel downloads use the same layout (backend).
 */
const esc = (v: unknown) =>
  String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const lines = (cell: string): [string, string, string] => {
  const p = (cell || "").split("\n");
  return [p[0] || "", p[1] || "", p[2] || ""];
};

export function printMuster(data: any, org: { OrgName?: string; OrgAddress?: string } | null, withLeave: boolean) {
  const cols: string[] = withLeave ? data.Columns || [] : [];
  const nd = data.DateHeaders.length;
  const heads = ["S.No", "Employee No", "Name", ...data.DateHeaders, ...cols, ...(withLeave ? ["Total", "Late Hrs", "Late Cl"] : ["Late Hrs"])];
  const ncols = heads.length;
  const wide = ncols > 40;
  const pt = Math.max(5.5, Math.min(9.5, 11 - Math.max(0, ncols - 12) * 0.18));

  const person = (e: any, sno: number) => {
    const ls = e.days.map(lines);
    const cell = (i: number, k: number, extra = "") => `<td class="r ${extra}">${esc(ls[i][k])}</td>`;
    const blanks = (n: number) => "<td></td>".repeat(n);
    const counts = cols.map((c) => `<td class="r b">${esc(e.Counts?.[c] ?? 0)}</td>`).join("");
    const tail = withLeave
      ? `<td class="r">${esc(e.Total)}</td><td>${esc(e.LateHrs)}</td><td class="r">${esc(e.LateCl)}</td>`
      : `<td>${esc(e.LateHrs)}</td>`;
    const tailBlank = blanks(cols.length + (withLeave ? 3 : 1));
    const range = Array.from({ length: nd }, (_, i) => i);
    return `<tbody class="emp">
<tr><td class="c">${sno}</td><td class="b">${esc(e.EmployeeCode)}</td><td class="c b">${esc(e.EmployeeName)}</td>${range.map((i) => cell(i, 0)).join("")}${counts}${tail}</tr>
<tr>${blanks(3)}${range.map((i) => cell(i, 1)).join("")}${tailBlank}</tr>
<tr>${blanks(3)}${range.map((i) => `<td class="b">${esc(ls[i][2])}</td>`).join("")}${tailBlank}</tr>
</tbody>`;
  };

  const body = (data.groups?.length ? data.groups : [{ Department: "", employees: data.employees }])
    .map((g: any) => {
      const head = g.Department ? `<tbody class="dept"><tr><td colspan="${ncols}">${esc(g.Department)}</td></tr></tbody>` : "";
      const people = g.employees.map((e: any, i: number) => person(e, g.Department ? e.SNo : i + 1)).join("");
      return `${head}${people}<tbody><tr class="gap">${"<td></td>".repeat(ncols)}</tr></tbody>`;
    })
    .join("");

  const cat = `Category : ${esc(data.Category)}${data.AttendanceCategory ? `&nbsp;&nbsp;&nbsp;Attendance Category : ${esc(data.AttendanceCategory)}` : ""}`;
  const stamp = new Date().toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })
    .replace(",", "");

  const w = window.open("", "_blank", "width=1100,height=800");
  if (!w) return;
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Attendance Report</title>
<style>
  @page { size: ${wide ? "A3" : "A4"} landscape; margin: 10mm 10mm 14mm; }
  body { font: ${pt}pt/1.25 "Book Antiqua", "Palatino Linotype", Palatino, "Times New Roman", serif; color: #000; margin: 0; }
  .head { text-align: center; margin-bottom: 6px; }
  .head .org { font-size: 13pt; font-weight: 700; }
  .head div { font-size: 10pt; }
  table { border-collapse: collapse; margin: 0 auto; }
  th, td { border: 1px dashed #000; padding: 0 2px; white-space: nowrap; text-align: left; height: ${pt * 1.35}pt; }
  th { background: #ff9; text-align: center; font-weight: 700; }
  thead { display: table-header-group; }
  td.c { text-align: center; } td.r { text-align: right; } .b { font-weight: 700; }
  .dept td { font-size: ${pt + 1.7}pt; font-weight: 700; border: 1px dashed #000; }
  tbody.emp { page-break-inside: avoid; }
  .foot { position: fixed; left: 0; bottom: 0; font-size: 8pt; }
</style></head><body>
<div class="head"><div class="org">${esc(org?.OrgName)}</div><div>${esc(org?.OrgAddress)}</div>
<div>Attendance Report From ${esc(data.FromLabel)} To ${esc(data.ToLabel)}</div><div>${cat}</div></div>
<table><thead><tr>${heads.map((h) => `<th>${esc(h)}</th>`).join("")}</tr><tr class="gap">${"<td></td>".repeat(ncols)}</tr></thead>${body}</table>
<div class="foot">Printed on:${esc(stamp)}</div>
</body></html>`);
  w.document.close();
  w.focus();
  setTimeout(() => { w.print(); }, 250);
}
