import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { Req } from "../../components/Req";
import { DEFAULT_ORG_NAME, DeptYearFilter, todayIso, toNum, useDepartments, useSchools, useStudentOptions } from "./common";

const EMPTY = {
  StudentCode: "", StudentName: "", DepartmentId: "", RegisteredYear: "", Batch: "",
  Category: "", SchoolId: "", Section: "", RollNo: "", DateOfBirth: "",
};

// CSV columns: code,name,department,registered_year,batch,category,section,roll_no
const CSV_HEADER = ["code", "name", "department", "registered_year", "batch", "category", "section", "roll_no"];

/** A ready-to-fill import file: the header plus two example rows that use this site's own departments and
 *  dropdown values, so it imports as it is. Opens in Excel (UTF-8 with BOM); save it back as CSV. */
function downloadSampleCsv(departments: any[], registeredYears: string[], batches: string[], categories: string[]) {
  const dept = (i: number) => departments[i % Math.max(departments.length, 1)]?.DepartmentName || "COMPUTER SCIENCE AND ENGINEERING";
  const pick = (list: string[], fallback: string) => list[0] || fallback;
  const cell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const lines = [
    CSV_HEADER,
    ["24CSE001", "Arun Kumar", dept(0), pick(registeredYears, "Jun 2024"), pick(batches, "2024"), pick(categories, "Full Time"), "A", "24CSE001"],
    ["24CSE002", "Priya S", dept(1), pick(registeredYears, "Jun 2024"), pick(batches, "2024"), pick(categories, "Full Time"), "B", "24CSE002"],
  ].map((r) => r.map(cell).join(","));
  const blob = new Blob(["\uFEFF" + lines.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "students-import-sample.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function parseCsv(text: string, departments: any[]) {
  const byName = new Map(departments.map((d) => [d.DepartmentName.trim().toLowerCase(), d.DepartmentId]));
  const rows: any[] = [];
  const errors: string[] = [];
  text.replace(/^\uFEFF/, "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean).forEach((line, i) => {
    const c = line.split(",").map((x) => x.trim().replace(/^"(.*)"$/, "$1").trim());
    if (i === 0 && /code/i.test(c[0])) return; // header
    const dept = byName.get((c[2] || "").toLowerCase());
    if (!c[0] || !c[1] || !dept) {
      errors.push(`Line ${i + 1}: needs code, name and a known department`);
      return;
    }
    rows.push({
      StudentCode: c[0], StudentName: c[1], DepartmentId: dept,
      RegisteredYear: c[3] || null, Batch: c[4] || null, Category: c[5] || null,
      Section: c[6] || null, RollNo: c[7] || null,
    });
  });
  return { rows, errors };
}

export function StudentsPage() {
  const departments = useDepartments();
  const schools = useSchools();
  const { registeredYears, batches, categories } = useStudentOptions();
  const [summary, setSummary] = useState<{ years: string[]; departments: any[] }>({ years: [], departments: [] });
  const [students, setStudents] = useState<any[]>([]);
  const [organizations, setOrganizations] = useState<any[]>([]);
  const [orgFilter, setOrgFilter] = useState(""); // "" = all institutions
  const [deptFilter, setDeptFilter] = useState("");
  const [regYearFilter, setRegYearFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20); // -1 = All
  const [form, setForm] = useState<any>(EMPTY);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [tab, setTab] = useState<"active" | "discontinued" | "completed">("active");
  const [leaving, setLeaving] = useState<{ s: any; kind: "discontinue" | "complete" } | null>(null);
  const [leaveDate, setLeaveDate] = useState(todayIso());
  const [leaveNote, setLeaveNote] = useState("");
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => {
    api.getStudents({ department_id: toNum(deptFilter), registered_year: regYearFilter || undefined, q: search || undefined, status: tab })
      .then(setStudents).catch((e) => setStatus({ text: e.message, ok: false }));
    api.getStudentSummary().then(setSummary).catch(() => setSummary({ years: [], departments: [] }));
  };
  useEffect(load, [deptFilter, regYearFilter, search, tab]);
  useEffect(() => {
    api.getOrganizations().then((orgs: any[]) => {
      setOrganizations(orgs);
      // Default to the institute's organization when present (req: default organization).
      const def = orgs.find((o) => (o.OrgName || "").trim() === DEFAULT_ORG_NAME);
      if (def) setOrgFilter(String(def.OrganizationId));
    }).catch(() => setOrganizations([]));
  }, []);
  useEffect(() => { setPage(1); }, [deptFilter, regYearFilter, search, tab, orgFilter, pageSize]);

  const set = (k: string, v: string) => setForm((f: any) => ({ ...f, [k]: v }));

  const openNew = () => {
    setEditingId(null);
    setForm({ ...EMPTY, DepartmentId: deptFilter, RegisteredYear: regYearFilter || "" });
    setShowForm(true);
  };
  const openEdit = (s: any) => {
    setEditingId(s.StudentId);
    setForm({
      ...EMPTY, ...Object.fromEntries(Object.entries(s).map(([k, v]) => [k, v ?? ""])),
      DepartmentId: String(s.DepartmentId),
      RegisteredYear: s.RegisteredYear || "", Batch: s.Batch || "", Category: s.Category || "",
      SchoolId: s.SchoolId ? String(s.SchoolId) : "",
    });
    setShowForm(true);
  };

  const save = async () => {
    const payload = {
      StudentCode: form.StudentCode, StudentName: form.StudentName,
      DepartmentId: Number(form.DepartmentId),
      RegisteredYear: form.RegisteredYear || null, Batch: form.Batch || null,
      Category: form.Category || null, SchoolId: form.SchoolId ? Number(form.SchoolId) : null,
      Section: form.Section || null, RollNo: form.RollNo || null,
      DateOfBirth: form.DateOfBirth || null, IsActive: "Y",
    };
    try {
      if (editingId) await api.updateStudent(editingId, payload);
      else await api.createStudent(payload);
      setStatus({ text: editingId ? "Student updated." : "Student added.", ok: true });
      setShowForm(false);
      load();
    } catch (e: any) {
      setStatus({ text: e.message || "Save failed", ok: false });
    }
  };

  const startLeaving = (s: any, kind: "discontinue" | "complete") => {
    setLeaving({ s, kind });
    setLeaveDate(todayIso());
    setLeaveNote("");
  };
  const confirmLeaving = async () => {
    if (!leaving) return;
    const body = { Date: leaveDate, Note: leaveNote || undefined };
    try {
      if (leaving.kind === "discontinue") await api.discontinueStudent(leaving.s.StudentId, body);
      else await api.completeStudent(leaving.s.StudentId, body);
      setStatus({ text: `${leaving.s.StudentName} ${leaving.kind === "discontinue" ? "discontinued" : "marked completed"} and moved to the archive.`, ok: true });
      setLeaving(null);
      load();
    } catch (e: any) { setStatus({ text: e.message, ok: false }); }
  };
  const restore = async (s: any) => {
    if (!window.confirm(`Restore ${s.StudentName} as an active student?`)) return;
    try { await api.restoreStudent(s.StudentId); setStatus({ text: `${s.StudentName} restored.`, ok: true }); load(); }
    catch (e: any) { setStatus({ text: e.message, ok: false }); }
  };

  const enroll = async (s: any) => {
    setStatus({ text: `Enrolling ${s.StudentName} from camera…`, ok: true });
    try {
      const r = await api.enrollStudentFromCamera(s.StudentCode);
      setStatus({ text: `Face enrolled for ${s.StudentName} (${r.enrolled_count} sample(s)).`, ok: true });
    } catch (e: any) {
      setStatus({ text: e.message || "Enrollment failed", ok: false });
    }
  };

  const onImport = async (file?: File) => {
    if (!file) return;
    const { rows, errors } = parseCsv(await file.text(), departments);
    if (!rows.length) { setStatus({ text: errors[0] || "No valid rows found.", ok: false }); return; }
    try {
      const r = await api.importStudents(rows);
      const bad = errors.length + r.errors.length;
      setStatus({ text: `Imported ${r.created} student(s)${bad ? `, ${bad} row(s) skipped` : ""}.`, ok: bad === 0 });
      load();
    } catch (e: any) {
      setStatus({ text: e.message || "Import failed", ok: false });
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  const deptName = (id: string) => departments.find((d) => String(d.DepartmentId) === id)?.DepartmentName;

  // Institution filter: students/departments belong to an organization via the department master.
  const deptOrg = new Map<number, string>(departments.map((d: any) => [Number(d.DepartmentId), String(d.OrganizationId ?? "")]));
  const inOrg = (deptId: any) => !orgFilter || deptOrg.get(Number(deptId)) === orgFilter;
  const deptsForOrg = orgFilter ? departments.filter((d: any) => String(d.OrganizationId ?? "") === orgFilter) : departments;
  const filteredStudents = students.filter((s: any) => inOrg(s.DepartmentId));
  const summaryDepts = summary.departments.filter((d: any) => inOrg(d.DepartmentId));
  const summaryYears = summary.years;
  // Client-side pagination of the (already server-filtered) list.
  const effSize = pageSize === -1 ? filteredStudents.length || 1 : pageSize;
  const totalPages = Math.max(1, Math.ceil(filteredStudents.length / effSize));
  const currentPage = Math.min(page, totalPages);
  const pageRows = filteredStudents.slice((currentPage - 1) * effSize, currentPage * effSize);

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Students</h2>
          <p className="sub">Student master data by department and registered year.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input ref={fileRef} type="file" accept=".csv" hidden onChange={(e) => onImport(e.target.files?.[0])} />
          <button className="btn-device-ghost" onClick={() => downloadSampleCsv(departments, registeredYears, batches, categories)}
            title="Download a sample file with the columns the import expects (code, name, department, registered year, batch, category, section, roll no)">
            Sample CSV
          </button>
          <button className="btn-device-ghost" onClick={() => fileRef.current?.click()} title="CSV: code,name,department,registered_year,batch,category,section,roll_no">Import CSV</button>
          <button className="btn btn-primary-purple" onClick={openNew}>+ Add Student</button>
        </div>
      </div>

      {status && <p className={status.ok ? "note-ok" : "note-err"}>{status.text}</p>}

      <div className="section-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Department × Registered Year</h3>
        {summaryDepts.length === 0 ? <p style={{ color: "var(--text-muted)" }}>No students yet.</p> : (
          <table className="table table-compact">
            <thead><tr><th>Department</th>{summaryYears.map((y) => <th key={y}>{y}</th>)}<th>Total</th></tr></thead>
            <tbody>
              {summaryDepts.map((d) => (
                <tr key={d.DepartmentId}>
                  <td><strong>{d.DepartmentName}</strong></td>
                  {summaryYears.map((y) => <td key={y}>{d.years[y] || 0}</td>)}
                  <td><strong>{d.total}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {leaving && (
        <div className="section-card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>{leaving.kind === "discontinue" ? "Discontinue" : "Mark completed:"} {leaving.s.StudentName}</h3>
          <p style={{ color: "var(--text-muted)", marginTop: 0 }}>
            Attendance stops and the student moves to the archive. Past attendance is kept, and you can restore them later.
          </p>
          <div className="form-row-2">
            <label>{leaving.kind === "discontinue" ? "Last day of attendance" : "Completion date"} <Req />
              <input type="date" value={leaveDate} max={todayIso()} onChange={(e) => setLeaveDate(e.target.value)} /></label>
            <label>Reason / note<input value={leaveNote} onChange={(e) => setLeaveNote(e.target.value)} placeholder="Optional" /></label>
          </div>
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button className="btn btn-primary-purple" onClick={confirmLeaving} disabled={!leaveDate}>Confirm</button>
            <button className="btn-device-ghost" onClick={() => setLeaving(null)}>Cancel</button>
          </div>
        </div>
      )}

      {showForm && (
        <div className="section-card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>{editingId ? "Edit Student" : "New Student"}</h3>
          <div className="form-row-2">
            <label><span>Student Code (Face ID) <Req /></span><input value={form.StudentCode} disabled={!!editingId} placeholder="e.g. CS24001" onChange={(e) => set("StudentCode", e.target.value)} />
              <small className="field-hint">The ID the camera or device uses to recognise this student. It links their face and punches to this record, so it must match the ID enrolled on the device. It cannot be changed after saving.</small></label>
            <label><span>Name <Req /></span><input value={form.StudentName} onChange={(e) => set("StudentName", e.target.value)} /></label>
            <label><span>Department <Req /></span>
              <select value={form.DepartmentId} onChange={(e) => set("DepartmentId", e.target.value)}>
                <option value="">Select…</option>
                {departments.map((d) => <option key={d.DepartmentId} value={d.DepartmentId}>{d.DepartmentName}</option>)}
              </select>
            </label>
            <label>Registered Year
              <select value={form.RegisteredYear} onChange={(e) => set("RegisteredYear", e.target.value)}>
                <option value="">Select…</option>
                {registeredYears.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <label>Batch
              <select value={form.Batch} onChange={(e) => set("Batch", e.target.value)}>
                <option value="">Select…</option>
                {batches.map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </label>
            <label>Category
              <select value={form.Category} onChange={(e) => set("Category", e.target.value)}>
                <option value="">Select…</option>
                {categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label>School
              <select value={form.SchoolId} onChange={(e) => set("SchoolId", e.target.value)}>
                <option value="">Select…</option>
                {schools.map((s) => <option key={s.SchoolId} value={s.SchoolId}>{s.SchoolName}</option>)}
              </select>
            </label>
            <label>Section<input value={form.Section} onChange={(e) => set("Section", e.target.value)} /></label>
            <label>Roll No<input value={form.RollNo} onChange={(e) => set("RollNo", e.target.value)} /></label>
            <label>Registered Date<input type="date" value={form.DateOfBirth} onChange={(e) => set("DateOfBirth", e.target.value)} /></label>
          </div>
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button className="btn btn-primary-purple" onClick={save}
              disabled={!form.StudentCode || !form.StudentName || !form.DepartmentId}>Save</button>
            <button className="btn-device-ghost" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="section-card">
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {([["active", "Active"], ["discontinued", "Discontinued"], ["completed", "Completed (archive)"]] as const).map(([k, label]) => (
            <button key={k} className={tab === k ? "btn btn-primary-purple" : "btn-device-ghost"} onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>
        <div className="form-row-2" style={{ marginBottom: 12 }}>
          <label>Institution
            <select value={orgFilter} onChange={(e) => {
              const v = e.target.value;
              setOrgFilter(v);
              if (v && deptFilter && deptOrg.get(Number(deptFilter)) !== v) setDeptFilter("");
            }}>
              <option value="">All institutions</option>
              {organizations.map((o) => <option key={o.OrganizationId} value={String(o.OrganizationId)}>{o.OrgName}</option>)}
            </select>
          </label>
          <DeptYearFilter departments={deptsForOrg} departmentId={deptFilter} registeredYear={regYearFilter}
            onDepartment={setDeptFilter} onRegisteredYear={setRegYearFilter} />
          <label>Search<input value={search} placeholder="Name, code or roll no" onChange={(e) => setSearch(e.target.value)} /></label>
        </div>
        <table className="table table-compact">
          <thead><tr><th>Code</th><th>Name</th><th>Department</th><th>Registered Year</th><th>Batch</th><th>Category</th><th>School</th><th>Section</th><th>Roll No</th>{tab !== "active" && <th>{tab === "completed" ? "Completed on" : "Left on"}</th>}<th /></tr></thead>
          <tbody>
            {pageRows.map((s) => (
              <tr key={s.StudentId}>
                <td>{s.StudentCode}</td>
                <td><strong>{s.StudentName}</strong></td>
                <td>{s.DepartmentName || deptName(String(s.DepartmentId))}</td>
                <td>{s.RegisteredYear}</td>
                <td>{s.Batch}</td>
                <td>{s.Category}</td>
                <td>{s.SchoolName}</td>
                <td>{s.Section}</td>
                <td>{s.RollNo}</td>
                {tab !== "active" && <td>{s.StatusDate}{s.StatusNote ? ` · ${s.StatusNote}` : ""}</td>}
                <td style={{ whiteSpace: "nowrap" }}>
                  {tab === "active" ? (
                    <>
                      <button className="btn-device-ghost" onClick={() => enroll(s)}>Enroll face</button>{" "}
                      <button className="btn-device-ghost" onClick={() => openEdit(s)}>Edit</button>{" "}
                      <button className="btn-device-ghost" onClick={() => startLeaving(s, "complete")}>Complete</button>{" "}
                      <button className="btn-device-ghost" onClick={() => startLeaving(s, "discontinue")}>Discontinue</button>
                    </>
                  ) : (
                    <button className="btn-device-ghost" onClick={() => restore(s)}>Restore</button>
                  )}
                </td>
              </tr>
            ))}
            {filteredStudents.length === 0 && <tr><td colSpan={11} style={{ color: "var(--text-muted)" }}>{tab === "active" ? "No students match the filter." : "Nothing in the archive yet."}</td></tr>}
          </tbody>
        </table>
        {filteredStudents.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Rows per page</span>
              <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} aria-label="Rows per page">
                {[10, 20, 30, 40, 50, 75, 100].map((n) => <option key={n} value={n}>{n}</option>)}
                <option value={-1}>All</option>
              </select>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button className="btn-device-ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={currentPage <= 1}>Previous</button>
              <span style={{ fontSize: 13 }}>Page {currentPage} of {totalPages}</span>
              <button className="btn-device-ghost" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage >= totalPages}>Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
