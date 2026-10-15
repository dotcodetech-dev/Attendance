/**
 * Shared filter bar for the staff attendance reports: a date range (with
 * Day / Week / Month / Year / Custom presets) plus Organization / Department /
 * Category / Employee Type selectors, in that order (the only report filters). The page owns the value; this renders
 * the fields (drop it inside a `.toolbar` next to the action buttons).
 */
import { useEffect, useState } from "react";

import { api } from "../api/client";

export interface ReportFilterValues {
  from: string;
  to: string;
  department: string;
  organizationId: string;
  employeeTypeId: string;
  categoryId: string;   // attendance category: "" = all, "0" = not assigned
}

const isoDate = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function emptyFilters(): ReportFilterValues {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  return {
    from: isoDate(first), to: isoDate(now),
    department: "", organizationId: "", employeeTypeId: "", categoryId: "",
  };
}

/** snake_case query object for the backend (get fns and downloadReport). */
export function filterQuery(f: ReportFilterValues, withRange = true): Record<string, string | undefined> {
  const q: Record<string, string | undefined> = {
    department: f.department || undefined,
    organization_id: f.organizationId || undefined,
    employee_type_id: f.employeeTypeId || undefined,
    category_id: f.categoryId || undefined,
  };
  if (withRange) {
    q.from_date = f.from || undefined;
    q.to_date = f.to || undefined;
  }
  return q;
}

export function ReportFilters({ value, onChange, withDateRange = true }: {
  value: ReportFilterValues;
  onChange: (v: ReportFilterValues) => void;
  withDateRange?: boolean;
}) {
  const [organizations, setOrganizations] = useState<any[]>([]);
  const [departments, setDepartments] = useState<any[]>([]);
  const [employeeTypes, setEmployeeTypes] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);

  useEffect(() => {
    api.getOrganizations().then(setOrganizations).catch(() => setOrganizations([]));
    api.getDepartments().then(setDepartments).catch(() => setDepartments([]));
    api.getEmployeeTypes().then(setEmployeeTypes).catch(() => setEmployeeTypes([]));
    api.getCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  const set = (patch: Partial<ReportFilterValues>) => onChange({ ...value, ...patch });

  const preset = (kind: "day" | "week" | "month" | "year") => {
    const now = new Date();
    let from = now, to = now;
    if (kind === "day") {
      from = to = now;
    } else if (kind === "week") {
      const dow = (now.getDay() + 6) % 7; // Monday = 0
      from = new Date(now); from.setDate(now.getDate() - dow);
      to = new Date(from); to.setDate(from.getDate() + 6);
    } else if (kind === "month") {
      from = new Date(now.getFullYear(), now.getMonth(), 1);
      to = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    } else if (kind === "year") {
      from = new Date(now.getFullYear(), 0, 1);
      to = new Date(now.getFullYear(), 11, 31);
    }
    set({ from: isoDate(from), to: isoDate(to) });
  };

  return (
    <>
      {withDateRange && (
        <>
          <div className="field field-sm"><label>From</label>
            <input type="date" value={value.from} onChange={(e) => set({ from: e.target.value })} /></div>
          <div className="field field-sm"><label>To</label>
            <input type="date" value={value.to} onChange={(e) => set({ to: e.target.value })} /></div>
          <div className="field"><label>Quick range</label>
            <div style={{ display: "flex", gap: 4 }}>
              {(["day", "week", "month", "year"] as const).map((k) => (
                <button key={k} type="button" className="btn btn-outline-reports"
                        onClick={() => preset(k)}
                        style={{ textTransform: "capitalize", padding: "0 10px" }}>{k}</button>
              ))}
            </div>
          </div>
        </>
      )}
      <div className="field"><label>Organization</label>
        <select value={value.organizationId}
                onChange={(e) => set({ organizationId: e.target.value, department: "" })}>
          <option value="">All organizations</option>
          {organizations.map((o) => <option key={o.OrganizationId} value={o.OrganizationId}>{o.OrgName}</option>)}
        </select>
      </div>
      <div className="field"><label>Department</label>
        <select value={value.department} onChange={(e) => set({ department: e.target.value })}>
          <option value="">All departments</option>
          {departments
            .filter((d) => !value.organizationId || d.OrganizationId === Number(value.organizationId))
            .map((d) => <option key={d.DepartmentId} value={d.DepartmentName}>{d.DepartmentName}</option>)}
        </select>
      </div>
      {/* Order fixed by the client: Organization, Department, Category, Employee Type. */}
      <div className="field"><label>Category</label>
        <select value={value.categoryId} onChange={(e) => set({ categoryId: e.target.value })}>
          <option value="">All categories</option>
          <option value="0">Not assigned</option>
          {categories.map((c) => (
            <option key={c.CategoryId} value={c.CategoryId}>{c.CategoryName}{c.IsActive === "Y" ? "" : " (inactive)"}</option>
          ))}
        </select>
      </div>
      <div className="field"><label>Employee Type</label>
        <select value={value.employeeTypeId} onChange={(e) => set({ employeeTypeId: e.target.value })}>
          <option value="">All types</option>
          {employeeTypes.map((t) => <option key={t.EmployeeTypeId} value={t.EmployeeTypeId}>{t.TypeName}</option>)}
        </select>
      </div>
    </>
  );
}
