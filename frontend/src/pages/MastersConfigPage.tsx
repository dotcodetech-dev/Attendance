import { useEffect, useState } from "react";

import { api } from "../api/client";

type Org = { OrganizationId: number; OrgName: string; Address?: string; IsActive: string };
type Dept = { DepartmentId: number; OrganizationId: number; DepartmentName: string; IsActive: string };
type EType = { EmployeeTypeId: number; TypeName: string; IsActive: string };
type Desig = { DesignationId: number; DesignationName: string; IsActive: string };
type SchoolRec = { SchoolId: number; SchoolName: string; IsActive: string };

type Row = { id: number; name: string; active: boolean };

/** One master list: inline rename, activate/deactivate, empty state. Scrolls inside its card. */
function MasterList({
  rows, emptyText, onRename, onToggle,
}: {
  rows: Row[];
  emptyText: string;
  onRename: (row: Row, name: string) => void;
  onToggle: (row: Row) => void;
}) {
  const [editId, setEditId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  const commit = (row: Row) => {
    const name = draft.trim();
    setEditId(null);
    if (name && name !== row.name) onRename(row, name);
  };

  if (rows.length === 0) return <div className="masters-empty">{emptyText}</div>;

  return (
    <ul className="masters-list">
      {rows.map((r) => (
        <li key={r.id} className={"masters-item" + (r.active ? "" : " is-inactive")}>
          {editId === r.id ? (
            <>
              <input
                className="masters-edit-input"
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commit(r);
                  if (e.key === "Escape") setEditId(null);
                }}
              />
              <div className="masters-actions">
                <button className="masters-btn masters-btn-primary" onClick={() => commit(r)}>Save</button>
                <button className="masters-btn" onClick={() => setEditId(null)}>Cancel</button>
              </div>
            </>
          ) : (
            <>
              <span className="masters-name">{r.name}</span>
              <span className={"badge " + (r.active ? "badge-green" : "badge-gray")}>{r.active ? "Active" : "Inactive"}</span>
              <div className="masters-actions">
                <button className="masters-btn" onClick={() => { setEditId(r.id); setDraft(r.name); }}>Rename</button>
                <button className="masters-btn" onClick={() => onToggle(r)}>{r.active ? "Deactivate" : "Activate"}</button>
              </div>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

function AddRow({
  value, placeholder, onChange, onAdd, disabled,
}: {
  value: string;
  placeholder: string;
  onChange: (v: string) => void;
  onAdd: () => void;
  disabled?: boolean;
}) {
  return (
    <form className="masters-add" onSubmit={(e) => { e.preventDefault(); if (!disabled) onAdd(); }}>
      <div className="masters-add-line">
        <input value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
        <button type="submit" className="btn btn-primary-purple" disabled={disabled}>Add</button>
      </div>
    </form>
  );
}

/** Every master shares this card, so they are all the same size: a fixed height, with the list scrolling inside. */
function MasterCard({
  title, count, hint, sub, children,
}: {
  title: string;
  count: number;
  hint?: string;
  sub?: React.ReactNode; // replaces the hint line (e.g. the Organization picker on Departments)
  children: React.ReactNode;
}) {
  return (
    <section className="masters-card">
      <header className="masters-card-head">
        <h3>{title}</h3>
        <span className="masters-count">{count}</span>
      </header>
      <div className="masters-sub">{sub ?? <p className="masters-hint">{hint}</p>}</div>
      {children}
    </section>
  );
}

export function MastersConfigPage() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [depts, setDepts] = useState<Dept[]>([]);
  const [types, setTypes] = useState<EType[]>([]);
  const [designations, setDesignations] = useState<Desig[]>([]);
  const [schools, setSchools] = useState<SchoolRec[]>([]);
  const [sopts, setSopts] = useState<{ RegisteredYear: any[]; Batch: any[]; Category: any[] }>({ RegisteredYear: [], Batch: [], Category: [] });
  const [newDesignation, setNewDesignation] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [newOrg, setNewOrg] = useState("");
  const [deptOrgId, setDeptOrgId] = useState<string>("");
  const [newDept, setNewDept] = useState("");
  const [newType, setNewType] = useState("");
  const [newSchool, setNewSchool] = useState("");
  const [newOpt, setNewOpt] = useState<{ RegisteredYear: string; Batch: string; Category: string }>({ RegisteredYear: "", Batch: "", Category: "" });

  const load = async () => {
    setError("");
    try {
      // Include inactive rows so a deactivated item stays listed and can be re-activated.
      const [o, d, t, g, s] = await Promise.all([
        api.getOrganizations(true), api.getDepartments(undefined, true), api.getEmployeeTypes(true),
        api.getDesignations(true), api.getSchools(true),
      ]);
      setOrgs(o);
      setDepts(d);
      setTypes(t);
      setDesignations(g);
      setSchools(s);
      if (!deptOrgId && o.length) setDeptOrgId(String(o[0].OrganizationId));
    } catch (e: any) {
      setError(e?.message || "Failed to load masters.");
    }
    // Student dropdown options load separately so a missing/older backend endpoint
    // can't blank the rest of the page.
    try {
      const so = await api.getStudentOptions(true);
      setSopts({ RegisteredYear: so.RegisteredYear || [], Batch: so.Batch || [], Category: so.Category || [] });
    } catch {
      setSopts({ RegisteredYear: [], Batch: [], Category: [] });
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const flash = (msg: string) => { setNotice(msg); window.setTimeout(() => setNotice(""), 2500); };
  const run = async (fn: () => Promise<any>, ok: string) => {
    setError("");
    try { await fn(); flash(ok); await load(); }
    catch (e: any) { setError(e?.message || "Operation failed."); }
  };

  const visibleDepts = depts.filter((d) => !deptOrgId || d.OrganizationId === Number(deptOrgId));

  const orgRows: Row[] = orgs.map((o) => ({ id: o.OrganizationId, name: o.OrgName, active: o.IsActive === "Y" }));
  const deptRows: Row[] = visibleDepts.map((d) => ({ id: d.DepartmentId, name: d.DepartmentName, active: d.IsActive !== "N" }));
  const schoolRows: Row[] = schools.map((s) => ({ id: s.SchoolId, name: s.SchoolName, active: s.IsActive !== "N" }));
  const typeRows: Row[] = types.map((t) => ({ id: t.EmployeeTypeId, name: t.TypeName, active: t.IsActive === "Y" }));
  const designationRows: Row[] = designations.map((g) => ({ id: g.DesignationId, name: g.DesignationName, active: g.IsActive !== "N" }));

  // Student dropdown masters (Registered Year / Batch / Category) share one table + endpoints.
  const optionCard = (type: "RegisteredYear" | "Batch" | "Category", title: string, hint: string, placeholder: string) => {
    const list = sopts[type] || [];
    const rows: Row[] = list.map((o: any) => ({ id: o.StudentOptionId, name: o.OptionValue, active: o.IsActive !== "N" }));
    return (
      <MasterCard title={title} count={list.length} hint={hint}>
        <AddRow
          value={newOpt[type]} placeholder={placeholder} onChange={(v) => setNewOpt((s) => ({ ...s, [type]: v }))} disabled={!newOpt[type].trim()}
          onAdd={() => run(() => api.createStudentOption({ OptionType: type, OptionValue: newOpt[type].trim() }).then(() => setNewOpt((s) => ({ ...s, [type]: "" }))), `${title} value added.`)}
        />
        <MasterList
          rows={rows} emptyText={`No ${title.toLowerCase()} values yet.`}
          onRename={(r, name) => run(() => api.updateStudentOption(r.id, { OptionValue: name }), `${title} value renamed.`)}
          onToggle={(r) => run(() => api.updateStudentOption(r.id, { IsActive: r.active ? "N" : "Y" }),
            r.active ? `${title} value deactivated.` : `${title} value activated.`)}
        />
      </MasterCard>
    );
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Organizations &amp; Masters</h2>
          <p className="sub">
            Manage organizations, departments, schools, designations, employee types and the student form dropdowns (registered years, batches, categories). Departments and schools are shared by employees and students.
          </p>
        </div>
      </div>

      {error && <p className="note-err">{error}</p>}
      {notice && <p className="note-ok">{notice}</p>}

      <div className="masters-grid">
        {/* Organizations */}
        <MasterCard title="Organizations" count={orgs.length} hint="The institutions or companies your staff belong to.">
          <AddRow
            value={newOrg} placeholder="New organization name" onChange={setNewOrg} disabled={!newOrg.trim()}
            onAdd={() => run(() => api.createOrganization({ OrgName: newOrg.trim() }).then(() => setNewOrg("")), "Organization added.")}
          />
          <MasterList
            rows={orgRows} emptyText="No organizations yet."
            onRename={(r, name) => {
              const o = orgs.find((x) => x.OrganizationId === r.id)!;
              run(() => api.updateOrganizationMaster(r.id, { OrgName: name, Address: o.Address, IsActive: o.IsActive }), "Organization renamed.");
            }}
            onToggle={(r) => {
              const o = orgs.find((x) => x.OrganizationId === r.id)!;
              run(() => api.updateOrganizationMaster(r.id, { OrgName: o.OrgName, Address: o.Address, IsActive: r.active ? "N" : "Y" }),
                r.active ? "Organization deactivated." : "Organization activated.");
            }}
          />
        </MasterCard>

        {/* Departments per organization */}
        <MasterCard
          title="Departments" count={visibleDepts.length}
          sub={(
            <label className="masters-select">
              <span>Organization</span>
              <select value={deptOrgId} onChange={(e) => setDeptOrgId(e.target.value)}>
                {orgs.map((o) => <option key={o.OrganizationId} value={o.OrganizationId}>{o.OrgName}</option>)}
              </select>
            </label>
          )}
        >
          <AddRow
            value={newDept} placeholder="New department name" onChange={setNewDept} disabled={!newDept.trim() || !deptOrgId}
            onAdd={() => run(() => api.createDepartment({ OrganizationId: Number(deptOrgId), DepartmentName: newDept.trim() }).then(() => setNewDept("")), "Department added.")}
          />
          <MasterList
            rows={deptRows} emptyText="No departments for this organization yet."
            onRename={(r, name) => {
              const d = depts.find((x) => x.DepartmentId === r.id)!;
              run(() => api.updateDepartment(r.id, { OrganizationId: d.OrganizationId, DepartmentName: name, IsActive: d.IsActive }), "Department renamed (employees updated).");
            }}
            onToggle={(r) => {
              const d = depts.find((x) => x.DepartmentId === r.id)!;
              run(() => api.updateDepartment(r.id, { OrganizationId: d.OrganizationId, DepartmentName: d.DepartmentName, IsActive: r.active ? "N" : "Y" }),
                r.active ? "Department deactivated." : "Department activated.");
            }}
          />
        </MasterCard>

        {/* Schools */}
        <MasterCard title="Schools" count={schools.length} hint="Pick a school on the employee form and filter reports by it, e.g. School of Computer Science.">
          <AddRow
            value={newSchool} placeholder="New school (e.g. School of Commerce)" onChange={setNewSchool} disabled={!newSchool.trim()}
            onAdd={() => run(() => api.createSchool({ SchoolName: newSchool.trim() }).then(() => setNewSchool("")), "School added.")}
          />
          <MasterList
            rows={schoolRows} emptyText="No schools yet."
            onRename={(r, name) => {
              const s = schools.find((x) => x.SchoolId === r.id)!;
              run(() => api.updateSchool(r.id, { SchoolName: name, IsActive: s.IsActive }), "School renamed.");
            }}
            onToggle={(r) => {
              const s = schools.find((x) => x.SchoolId === r.id)!;
              run(() => api.updateSchool(r.id, { SchoolName: s.SchoolName, IsActive: r.active ? "N" : "Y" }),
                r.active ? "School deactivated." : "School activated.");
            }}
          />
        </MasterCard>

        {/* Designations */}
        <MasterCard title="Designations" count={designations.length} hint="Job titles, ranked in reports.">
          <AddRow
            value={newDesignation} placeholder="New designation (e.g. Professor)" onChange={setNewDesignation} disabled={!newDesignation.trim()}
            onAdd={() => run(() => api.createDesignation({ DesignationName: newDesignation.trim() }).then(() => setNewDesignation("")), "Designation added.")}
          />
          <MasterList
            rows={designationRows} emptyText="No designations yet."
            onRename={(r, name) => {
              const g = designations.find((x) => x.DesignationId === r.id)!;
              run(() => api.updateDesignation(r.id, { DesignationName: name, IsActive: g.IsActive }), "Designation renamed (employees updated).");
            }}
            onToggle={(r) => {
              const g = designations.find((x) => x.DesignationId === r.id)!;
              run(() => api.updateDesignation(r.id, { DesignationName: g.DesignationName, IsActive: r.active ? "N" : "Y" }),
                r.active ? "Designation deactivated." : "Designation activated.");
            }}
          />
        </MasterCard>

        {/* Employee types */}
        <MasterCard title="Employee Types" count={types.length} hint="Staff, faculty, contract and so on.">
          <AddRow
            value={newType} placeholder="New type (e.g. PhD Student)" onChange={setNewType} disabled={!newType.trim()}
            onAdd={() => run(() => api.createEmployeeType({ TypeName: newType.trim() }).then(() => setNewType("")), "Employee type added.")}
          />
          <MasterList
            rows={typeRows} emptyText="No types yet."
            onRename={(r, name) => {
              const t = types.find((x) => x.EmployeeTypeId === r.id)!;
              run(() => api.updateEmployeeType(r.id, { TypeName: name, IsActive: t.IsActive }), "Type renamed.");
            }}
            onToggle={(r) => {
              const t = types.find((x) => x.EmployeeTypeId === r.id)!;
              run(() => api.updateEmployeeType(r.id, { TypeName: t.TypeName, IsActive: r.active ? "N" : "Y" }),
                r.active ? "Type deactivated." : "Type activated.");
            }}
          />
        </MasterCard>

        {/* Student dropdowns — drive the Students registration form, so they are not hardcoded. */}
        {optionCard("RegisteredYear", "Student Registered Years", "Admission sessions shown on the Students form, e.g. Jan 2026.", "New registered year (e.g. Jan 2026)")}
        {optionCard("Batch", "Student Batches", "Batch values shown on the Students form, e.g. 2026.", "New batch (e.g. 2026)")}
        {optionCard("Category", "Student Categories", "Category values shown on the Students form, e.g. Full Time.", "New category (e.g. Full Time)")}
      </div>
    </div>
  );
}
