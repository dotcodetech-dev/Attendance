import { useState } from "react";

import { api } from "../../api/client";
import { SectionHead } from "../../components/ConfigUi";
import { Icons } from "../../components/SidebarIcons";

// Target fields the importer can map columns onto (must match backend student_import.FIELDS).
const FIELD_LABELS: Record<string, string> = {
  StudentCode: "Face ID / Code (device ID)",
  StudentName: "Student name",
  RollNo: "Roll No / Register No",
  Department: "Department",
  School: "School",
  RegisteredYear: "Registered Year (e.g. Jul 2021)",
  Batch: "Batch (admission year)",
  Category: "Category (Full / Part Time)",
  Section: "Section",
  RegisteredDate: "Registered Date",
  Status: "Status",
};

type Column = { index: number; letter: string; header: string | null; samples: string[] };
type Preview = {
  organization: string;
  summary: { total: number; to_create: number; to_update: number; skipped: number; errors: number; staff_duplicates: number; created?: number; updated?: number };
  rows: { row_number: number; StudentCode?: string; StudentName?: string; RollNo?: string; Department?: string; School?: string; action: string; messages: string[] }[];
  masters_created: { schools: string[]; departments: string[] };
};

/**
 * Import students from Excel (.xlsx) or CSV, the same way as Employees -> Import from Excel: the header row is
 * found (title rows above it are fine), each column is matched to a field (changeable), the organization is
 * suggested, and a full preview shows what will be added, updated or skipped before anything is saved.
 */
export function StudentImport({ organizations, onClose, onDone }: {
  organizations: { OrganizationId: number; OrgName: string }[];
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [columns, setColumns] = useState<Column[]>([]);
  const [fields, setFields] = useState<string[]>(Object.keys(FIELD_LABELS));
  const [colToField, setColToField] = useState<Record<number, string>>({});
  const [headerRow, setHeaderRow] = useState(1);
  const [orgId, setOrgId] = useState<string>("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [show, setShow] = useState<"all" | "problems">("problems");

  const mappingOf = (c2f: Record<number, string>, row: number, org: string) => {
    const cols: Record<string, number> = {};
    Object.entries(c2f).forEach(([idx, f]) => { if (f) cols[f] = Number(idx); });
    return { header_row: row, columns: cols, organization_id: org ? Number(org) : null };
  };
  const runPreview = async (f: File, c2f: Record<number, string>, row: number, org: string) => {
    if (!org) { setPreview(null); return; }
    setBusy(true); setError("");
    try { setPreview(await api.studentImportPreview(f, mappingOf(c2f, row, org))); }
    catch (e) { setPreview(null); setError(e instanceof Error ? e.message : "Could not read the file."); }
    finally { setBusy(false); }
  };

  const choose = async (f: File | null) => {
    if (!f) return;
    setFile(f); setPreview(null); setColumns([]); setColToField({}); setError(""); setBusy(true);
    try {
      const res = await api.studentImportInspect(f);
      const c2f: Record<number, string> = {};
      Object.entries(res.guessed_mapping || {}).forEach(([field, idx]) => { c2f[Number(idx)] = field; });
      const org = res.suggested_organization_id ? String(res.suggested_organization_id) : "";
      setColumns(res.columns || []); setFields(res.fields || Object.keys(FIELD_LABELS));
      setHeaderRow(res.header_row || 1); setColToField(c2f); setOrgId(org);
      setBusy(false);
      await runPreview(f, c2f, res.header_row || 1, org);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read the file."); setBusy(false);
    }
  };
  const setCol = (idx: number, field: string) => {
    const next: Record<number, string> = {};
    Object.entries(colToField).forEach(([i, f]) => { if (Number(i) !== idx && f !== field) next[Number(i)] = f; });
    if (field) next[idx] = field;
    setColToField(next);
    if (file) runPreview(file, next, headerRow, orgId);
  };
  const commit = async () => {
    if (!file || !preview) return;
    setBusy(true); setError("");
    try {
      const r: Preview = await api.studentImportCommit(file, mappingOf(colToField, headerRow, orgId));
      const s = r.summary;
      onDone(`Imported into ${r.organization}: ${s.created ?? s.to_create} student(s) added, ${s.updated ?? s.to_update} updated`
        + (s.skipped ? `, ${s.skipped} skipped` : "") + (s.errors ? `, ${s.errors} with errors` : "") + "."
        + (s.staff_duplicates ? ` ${s.staff_duplicates} also have a reader-created staff record: remove those with Employees → Clean up student records.` : ""));
    } catch (e) { setError(e instanceof Error ? e.message : "Import failed."); setBusy(false); }
  };

  const mapped = new Set(Object.values(colToField));
  const missing = ["StudentCode", "StudentName", "Department"].filter((f) => !mapped.has(f));
  const rows = (preview?.rows || []).filter((r) => show === "all" || r.action === "error" || r.action === "skip" || r.messages.length);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Import students" style={{ maxWidth: 980 }}>
        <div className="emp-edit-card">
          <div className="emp-edit-head">
            <div className="emp-edit-title">
              <span className="emp-avatar" aria-hidden>⇪</span>
              <div>
                <h3>Import students from Excel or CSV</h3>
                <span className="emp-edit-sub">Choose the file, check the columns and the organization, then confirm.</span>
              </div>
            </div>
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close">×</button>
          </div>

          <div className="emp-edit-scroll">
            {error && <div className="emp-error" role="alert">{error}</div>}

            <section className="emp-section">
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
                <input type="file" accept=".xlsx,.csv" onChange={(e) => choose(e.target.files?.[0] ?? null)} disabled={busy} aria-label="Excel or CSV file" />
                {busy && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Reading…</span>}
              </div>
              <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--text-muted)" }}>
                .xlsx or .csv. Title rows above the header are fine. Students are matched by Face ID: existing ones are updated.
                Missing schools and departments are created in the organization you choose.
              </p>
            </section>

            {file && columns.length > 0 && (
              <section className="emp-section">
                <SectionHead icon={Icons.document} title="Organization and columns" desc="Which institution these students belong to, and what each column holds." />
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 16, marginBottom: 12 }}>
                  <div className="field" style={{ minWidth: 260 }}>
                    <label htmlFor="si-org">Organization</label>
                    <select id="si-org" value={orgId} disabled={busy}
                      onChange={(e) => { setOrgId(e.target.value); runPreview(file, colToField, headerRow, e.target.value); }}>
                      <option value="">— Choose —</option>
                      {organizations.map((o) => <option key={o.OrganizationId} value={String(o.OrganizationId)}>{o.OrgName}</option>)}
                    </select>
                  </div>
                  <div className="field" style={{ width: 130 }}>
                    <label htmlFor="si-header">Header row</label>
                    <input id="si-header" type="number" min={1} value={headerRow} disabled={busy}
                      onChange={(e) => { const v = Math.max(1, Number(e.target.value) || 1); setHeaderRow(v); runPreview(file, colToField, v, orgId); }} />
                  </div>
                </div>
                {missing.length > 0 && <p className="note-err" style={{ marginTop: 0 }}>Map a column to: {missing.map((f) => FIELD_LABELS[f]).join(", ")}.</p>}
                <div style={{ overflowX: "auto", maxHeight: 300 }}>
                  <table className="table">
                    <thead><tr><th>Column</th><th>Sample values</th><th>Import as</th></tr></thead>
                    <tbody>
                      {columns.map((col) => (
                        <tr key={col.index}>
                          <td style={{ whiteSpace: "nowrap" }}><strong>{col.letter}</strong>{col.header ? ` · ${col.header}` : ""}</td>
                          <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{col.samples.join(", ") || "—"}</td>
                          <td>
                            <select value={colToField[col.index] || ""} onChange={(e) => setCol(col.index, e.target.value)} disabled={busy}>
                              <option value="">— Ignore —</option>
                              {fields.map((f) => <option key={f} value={f}>{FIELD_LABELS[f] || f}</option>)}
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {preview && (
              <section className="emp-section">
                <SectionHead icon={Icons.employees} title="Preview" desc={`Into ${preview.organization}. Nothing is saved until you click Import.`} />
                <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 10, fontSize: 14 }}>
                  <span><strong>{preview.summary.total}</strong> rows</span>
                  <span style={{ color: "#16a34a" }}><strong>{preview.summary.to_create}</strong> to add</span>
                  <span style={{ color: "#2563eb" }}><strong>{preview.summary.to_update}</strong> to update</span>
                  <span style={{ color: "#b7791f" }}><strong>{preview.summary.skipped}</strong> skipped</span>
                  <span style={{ color: "#dc2626" }}><strong>{preview.summary.errors}</strong> errors</span>
                </div>
                {(preview.masters_created.schools.length > 0 || preview.masters_created.departments.length > 0) && (
                  <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "0 0 10px" }}>
                    Will also add {preview.masters_created.schools.length} school(s){preview.masters_created.schools.length ? ` (${preview.masters_created.schools.join(", ")})` : ""}
                    {" "}and {preview.masters_created.departments.length} department(s) to {preview.organization}.
                  </p>
                )}
                {preview.summary.staff_duplicates > 0 && (
                  <p style={{ fontSize: 13, color: "#b7791f", margin: "0 0 10px" }}>
                    {preview.summary.staff_duplicates} of them also have a staff record the readers created (name = ID). After importing,
                    remove those with Employees → Clean up student records.
                  </p>
                )}
                <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                  <button type="button" className={"btn-device-ghost" + (show === "problems" ? " is-on" : "")} onClick={() => setShow("problems")}>Skipped, errors, notes</button>
                  <button type="button" className={"btn-device-ghost" + (show === "all" ? " is-on" : "")} onClick={() => setShow("all")}>All rows</button>
                </div>
                <div style={{ maxHeight: 280, overflow: "auto" }}>
                  {rows.length === 0 ? <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No problems: every row will be imported.</p> : (
                    <table className="table">
                      <thead style={{ position: "sticky", top: 0, background: "#f8fafc" }}>
                        <tr><th>Row</th><th>Face ID</th><th>Name</th><th>Roll No</th><th>Department</th><th>School</th><th>Action</th><th>Notes</th></tr>
                      </thead>
                      <tbody>
                        {rows.slice(0, 300).map((r) => (
                          <tr key={r.row_number}>
                            <td>{r.row_number}</td><td>{r.StudentCode ?? "—"}</td><td>{r.StudentName ?? "—"}</td><td>{r.RollNo ?? "—"}</td>
                            <td>{r.Department ?? "—"}</td><td>{r.School ?? "—"}</td>
                            <td><span className={"badge " + (r.action === "error" ? "badge-red" : r.action === "skip" ? "badge-amber" : r.action === "update" ? "badge-blue" : "badge-green")}>{r.action}</span></td>
                            <td style={{ fontSize: 12, color: r.action === "error" ? "#dc2626" : "var(--text-muted)" }}>{r.messages.join(" ")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                {rows.length > 300 && <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Showing the first 300 of {rows.length}.</p>}
              </section>
            )}

            <div className="emp-edit-actions">
              <button type="button" className="btn btn-outline-reports" onClick={onClose}>Cancel</button>
              <button type="button" className="btn btn-primary-purple" onClick={commit}
                disabled={busy || !preview || missing.length > 0 || preview.summary.to_create + preview.summary.to_update === 0}>
                {busy ? "Working…" : `Import ${(preview?.summary.to_create ?? 0) + (preview?.summary.to_update ?? 0)} students`}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
