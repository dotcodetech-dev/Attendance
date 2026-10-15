import { useEffect, useMemo, useRef, useState } from "react";

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

const MAX_MATCHES = 50;

/** "Name · Employee Code" for a person (Face ID too when it differs from the Employee Code). */
function employeeLabel(e: any): string {
  const code = e.StringCode || e.EmployeeCode;
  const face = e.StringCode && String(e.StringCode) !== String(e.EmployeeCode) ? ` · Face ID ${e.EmployeeCode}` : "";
  return `${e.EmployeeName || "(no name)"} · ${code}${face}`;
}

/**
 * Type-to-search employee picker: matches name, Employee Code, Face ID or Sort No and lists the hits.
 * Value is the Face ID (EmployeeCode), the same as EmployeeSelect, so it can replace it.
 */
export function EmployeeSearch({
  employees, value, onChange, id, placeholder = "Type name, Employee Code or Sort No…", style,
}: {
  employees: any[];
  value: string;
  onChange: (code: string) => void;
  id?: string;
  placeholder?: string;
  style?: React.CSSProperties;
}) {
  const selected = employees.find((e) => String(e.EmployeeCode) === value);
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  // Show the chosen person in the box. (Not on a cleared value: that is the user typing a new search.)
  useEffect(() => { if (selected) setText(employeeLabel(selected)); }, [selected]);

  useEffect(() => {
    const close = (ev: MouseEvent) => { if (boxRef.current && !boxRef.current.contains(ev.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const matches = useMemo(() => {
    const q = text.trim().toLowerCase();
    if (!q || (selected && text === employeeLabel(selected))) return employees.slice(0, MAX_MATCHES);
    return employees
      .filter((e) => [e.EmployeeName, e.StringCode, e.EmployeeCode, e.ShortNo]
        .some((v) => v != null && String(v).toLowerCase().includes(q)))
      .slice(0, MAX_MATCHES);
  }, [employees, text, selected]);

  const pick = (e: any) => {
    onChange(String(e.EmployeeCode));
    setText(employeeLabel(e));
    setOpen(false);
  };

  const onKey = (ev: React.KeyboardEvent<HTMLInputElement>) => {
    if (ev.key === "ArrowDown") { ev.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, matches.length - 1)); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (ev.key === "Enter" && open && matches[active]) { ev.preventDefault(); pick(matches[active]); }
    else if (ev.key === "Escape") setOpen(false);
  };

  return (
    <div ref={boxRef} style={{ position: "relative", ...style }}>
      <input
        id={id}
        type="search"
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        value={text}
        placeholder={placeholder}
        style={{ width: "100%" }}
        onFocus={(ev) => { ev.target.select(); setOpen(true); setActive(0); }}
        onChange={(ev) => {
          setText(ev.target.value);
          setOpen(true);
          setActive(0);
          if (value) onChange("");   // typing again drops the previous choice until a new one is picked
        }}
        onKeyDown={onKey}
      />
      {open && (
        <ul role="listbox" style={{
          position: "absolute", zIndex: 30, left: 0, right: 0, top: "calc(100% + 4px)", margin: 0, padding: 4,
          listStyle: "none", maxHeight: 300, overflowY: "auto", background: "var(--surface)",
          border: "1px solid var(--line)", borderRadius: "var(--radius)", boxShadow: "var(--shadow-md)",
        }}>
          {matches.length === 0 ? (
            <li style={{ padding: "8px 10px", color: "var(--text-muted)" }}>No employee matches “{text.trim()}”.</li>
          ) : matches.map((e, i) => (
            <li
              key={e.EmployeeId ?? e.EmployeeCode}
              role="option"
              aria-selected={i === active}
              onMouseDown={(ev) => { ev.preventDefault(); pick(e); }}
              onMouseEnter={() => setActive(i)}
              style={{
                padding: "7px 10px", borderRadius: 6, cursor: "pointer",
                background: i === active ? "var(--primary-soft)" : undefined,
              }}
            >
              <span style={{ fontWeight: 600 }}>{e.EmployeeName || "(no name)"}</span>
              <span style={{ color: "var(--text-muted)", marginLeft: 8, fontSize: 13 }}>
                {e.StringCode || e.EmployeeCode}
                {e.StringCode && String(e.StringCode) !== String(e.EmployeeCode) ? ` · Face ID ${e.EmployeeCode}` : ""}
                {e.ShortNo != null && String(e.ShortNo).trim() !== "" ? ` · Sort No ${e.ShortNo}` : ""}
                {e.Department ? ` · ${e.Department}` : ""}
              </span>
            </li>
          ))}
          {matches.length === MAX_MATCHES && (
            <li style={{ padding: "6px 10px", color: "var(--text-muted)", fontSize: 12 }}>Showing the first {MAX_MATCHES}; type more to narrow down.</li>
          )}
        </ul>
      )}
    </div>
  );
}
