import { useEffect, useState } from "react";

import { api } from "../api/client";

/** Employees for pickers. One request per page; an empty list if it fails. */
export function useEmployees() {
  const [employees, setEmployees] = useState<any[]>([]);
  useEffect(() => {
    api.getEmployees().then(setEmployees).catch(() => setEmployees([]));
  }, []);
  return employees;
}

/** Dropdown of employees by name and code. Value is the Employee Code. */
export function EmployeeSelect({
  employees, value, onChange, id, required, placeholder = "Select employee…", style,
}: {
  employees: any[];
  value: string;
  onChange: (code: string) => void;
  id?: string;
  required?: boolean;
  placeholder?: string;
  style?: React.CSSProperties;
}) {
  const known = employees.some((e) => String(e.EmployeeCode) === value);
  return (
    <select id={id} value={value} required={required} onChange={(e) => onChange(e.target.value)} style={style}>
      <option value="">{placeholder}</option>
      {value && !known && <option value={value}>{value}</option>}
      {employees.map((e) => (
        <option key={e.EmployeeId} value={e.EmployeeCode}>{e.EmployeeName} ({e.EmployeeCode})</option>
      ))}
    </select>
  );
}
