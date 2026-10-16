import { useEffect, useState } from "react";

import { api } from "../../api/client";

export const YEARS = [1, 2, 3, 4];

// Default organization for this deployment (Avinashilingam Institute).
export const DEFAULT_ORG_NAME = "Avinashilingam Institute for Home Science and Higher Education for Women";

export type StudentOptions = { registeredYears: string[]; batches: string[]; categories: string[] };

/** Registered Year / Batch / Category values, configured in Org & Masters (not hardcoded). */
export function useStudentOptions(): StudentOptions {
  const [opts, setOpts] = useState<StudentOptions>({ registeredYears: [], batches: [], categories: [] });
  useEffect(() => {
    api.getStudentOptions().then((g: any) => setOpts({
      registeredYears: (g.RegisteredYear || []).map((o: any) => o.OptionValue),
      batches: (g.Batch || []).map((o: any) => o.OptionValue),
      categories: (g.Category || []).map((o: any) => o.OptionValue),
    })).catch(() => setOpts({ registeredYears: [], batches: [], categories: [] }));
  }, []);
  return opts;
}

/** Active schools from the Org & Masters → School master. */
export function useSchools() {
  const [schools, setSchools] = useState<any[]>([]);
  useEffect(() => {
    api.getSchools().then(setSchools).catch(() => setSchools([]));
  }, []);
  return schools;
}

export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export function useDepartments(refreshKey = 0) {
  const [departments, setDepartments] = useState<any[]>([]);
  useEffect(() => {
    api.getDepartments().then((d: any[]) => setDepartments(d.filter((x) => x.IsActive !== "N"))).catch(() => setDepartments([]));
  }, [refreshKey]);
  return departments;
}

export function DeptYearFilter({
  departments, departmentId, registeredYear, onDepartment, onRegisteredYear,
}: {
  departments: any[];
  departmentId: string;
  registeredYear: string;
  onDepartment: (v: string) => void;
  onRegisteredYear: (v: string) => void;
}) {
  const { registeredYears } = useStudentOptions();
  // Always include the current value even if it was later deactivated, so the filter still shows it.
  const years = registeredYear && !registeredYears.includes(registeredYear)
    ? [registeredYear, ...registeredYears] : registeredYears;
  return (
    <>
      <label>Department
        <select value={departmentId} onChange={(e) => onDepartment(e.target.value)}>
          <option value="">All departments</option>
          {departments.map((d) => <option key={d.DepartmentId} value={d.DepartmentId}>{d.DepartmentName}</option>)}
        </select>
      </label>
      <label>Registered Year
        <select value={registeredYear} onChange={(e) => onRegisteredYear(e.target.value)}>
          <option value="">All registered years</option>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </label>
    </>
  );
}

const YEAR_NAMES = ["First year", "Second year", "Third year", "Fourth year"];

/** Year-of-study picker: four large cards instead of a dropdown. */
export function YearCards({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="year-cards" role="radiogroup" aria-label="Year of study">
      {YEARS.map((y) => (
        <button key={y} type="button" role="radio" aria-checked={value === String(y)}
          className={"year-card" + (value === String(y) ? " on" : "")} onClick={() => onChange(String(y))}>
          <b>{y}</b>
          <span>{YEAR_NAMES[y - 1]}</span>
        </button>
      ))}
    </div>
  );
}

export const toNum =(v: string) => (v ? Number(v) : undefined);
