import { FormEvent, useCallback, useEffect, useState } from "react";

import { Link } from "react-router-dom";

import { api, getBackendBaseUrl } from "../api/client";
import { BtnSpinner, LoadingNote } from "../components/LoadingNote";
import { Req } from "../components/Req";
import { Icons } from "../components/SidebarIcons";
import { useCampusOrg } from "../store/me";

function initialsOf(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

/** Department names are free text on the employee: compare ignoring case and extra spaces. */
const normDept = (name: unknown) => String(name ?? "").trim().replace(/\s+/g, " ").toLowerCase();

function SectionHead({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="emp-sech">
      <span className="emp-tile" aria-hidden>{icon}</span>
      <div>
        <h4>{title}</h4>
        <p>{desc}</p>
      </div>
    </div>
  );
}

type CategoryOption = { CategoryId: number; CategoryName: string };

// Full HR profile edit form. Every field is optional except Name.
const HR_FIELDS = [
  "EmployeeName", "StringCode", "ShortNo", "Department", "Designation", "Role", "CategoryId", "JoiningDate", "CurrentStatus",
  "DateOfBirth", "GuardianName", "MaritalStatus", "BloodGroup", "Address",
  "ContactNo", "OfficialNo", "EmergencyNo", "PersonalEmail", "OfficialEmail",
  "AadharNo", "PanNo", "UAN", "Salary",
  "EmployeeRFIDNumber",
  "LastWorkingDay", "ReasonForLeaving", "OrganizationId", "EmployeeTypeId", "SchoolId",
] as const;
type EditForm = Record<(typeof HR_FIELDS)[number], string>;
const BLANK_EDIT: EditForm = HR_FIELDS.reduce((acc, k) => ({ ...acc, [k]: "" }), {} as EditForm);
const blankEdit = (): EditForm => ({ ...BLANK_EDIT, Role: "Employee", CurrentStatus: "Active" });

// Target fields the Excel importer can map spreadsheet columns onto (must match backend IMPORT_FIELDS).
const IMPORT_FIELD_LABELS: Record<string, string> = {
  EmployeeCode: "Face ID (device code)",
  HrCode: "Employee Code (HR number)",
  ShortNo: "Sort No",
  EmployeeName: "Employee Name",
  EmployeeRFIDNumber: "Access Card / RFID",
  Department: "Department",
  Designation: "Designation",
  EmployeeType: "Employee Type",
  Organization: "Organization / Company",
  DateOfBirth: "Date of Birth",
  JoiningDate: "Joining Date",
  CurrentStatus: "Status",
  School: "School",
};

// Employee, Manager (HOD), Principal (Director), Admin. Manager and Principal are the two leave approvers.
const ROLE_OPTIONS = ["Employee", "Manager", "Principal", "Admin"];
const ROLE_LABEL: Record<string, string> = { Manager: "Manager / HOD", Principal: "Principal / Director" };

const ALPHANUM ="abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
const PASSWORD_CHARS = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789!@#$%&*";
function randomString(chars: string, length: number): string {
  let s = "";
  for (let i = 0; i < length; i++) s += chars[Math.floor(Math.random() * chars.length)];
  return s;
}
function generateCredentials(): { username: string; password: string } {
  return {
    username: "user_" + randomString(ALPHANUM, 8),
    password: randomString(PASSWORD_CHARS, 12),
  };
}

export function EmployeesPage() {
  // A campus-role login works inside one institution: every institution list on this page offers only that one.
  const campus = useCampusOrg();
  const [campusRoleNames, setCampusRoleNames] = useState<string[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [deviceOpsStatus, setDeviceOpsStatus] = useState("");
  // Delete dialog: what will be removed, and whether the readers drop the person too.
  const [delTarget, setDelTarget] = useState<any | null>(null);
  const [delPreview, setDelPreview] = useState<any | null>(null);
  const [delReaders, setDelReaders] = useState(true);
  const [deleting, setDeleting] = useState(false);
  // Students that were created as staff by a shared reader.
  const [dupOpen, setDupOpen] = useState(false);
  const [dups, setDups] = useState<any[] | null>(null);
  const [dupBusy, setDupBusy] = useState(false);
  const [editingEmployeeId, setEditingEmployeeId] = useState<number | null>(null);
  const [editingEmployeeCode, setEditingEmployeeCode] = useState<string>("");
  const [editForm, setEditForm] = useState<EditForm>(blankEdit());
  const [portalLoginUsername, setPortalLoginUsername] = useState("");
  const [portalLoginPassword, setPortalLoginPassword] = useState("");
  const [portalMessage, setPortalMessage] = useState("");
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [backendChecking, setBackendChecking] = useState(false);
  // Add-only fields; every other field lives in editForm and is shared with Edit.
  const [form, setForm] = useState({ EmployeeCode: "", LoginName: "", LoginPassword: "" });
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  // Enrolled face samples for the employee being edited: null = checking, -1 = could not check.
  const [faceCount, setFaceCount] = useState<number | null>(null);
  const [allOrganizations, setOrganizations] = useState<any[]>([]);
  const organizations = campus ? allOrganizations.filter((o) => o.OrganizationId === campus.id) : allOrganizations;
  const [departmentsList, setDepartmentsList] = useState<any[]>([]);
  const [employeeTypes, setEmployeeTypes] = useState<any[]>([]);
  const [schools, setSchools] = useState<any[]>([]);
  const [designationsList, setDesignationsList] = useState<any[]>([]);
  const [syncOptions, setSyncOptions] = useState({
    include_face: true,
    include_finger: true,
    include_card: true,
    include_photo: true,
  });
  const [importing, setImporting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  // Excel import modal state.
  const [xlOpen, setXlOpen] = useState(false);
  const [xlFile, setXlFile] = useState<File | null>(null);
  const [xlColumns, setXlColumns] = useState<any[]>([]);
  const [xlHeaderRow, setXlHeaderRow] = useState(1);
  const [xlFields, setXlFields] = useState<string[]>([]);
  const [xlColToField, setXlColToField] = useState<Record<number, string>>({});
  const [xlPreview, setXlPreview] = useState<any | null>(null);
  const [xlBusy, setXlBusy] = useState(false);
  const [xlError, setXlError] = useState("");
  // Bulk "move" selection state.
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [moveOpen, setMoveOpen] = useState(false);
  const [moveOrg, setMoveOrg] = useState("");
  const [moveDept, setMoveDept] = useState("");
  const [moveSchool, setMoveSchool] = useState("");
  const [moving, setMoving] = useState(false);
  // Shifts: the form creates / changes a roster entry; "Assign shift" does it for the selected rows.
  const [shifts, setShifts] = useState<any[]>([]);
  const [shiftId, setShiftId] = useState("");
  const [shiftWas, setShiftWas] = useState("");
  const [shiftFrom, setShiftFrom] = useState("");
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignShiftId, setAssignShiftId] = useState("");
  const [assignFrom, setAssignFrom] = useState("");
  const [assignTo, setAssignTo] = useState("");
  const [assigning, setAssigning] = useState(false);
  // Change-code (edit dialog) state.
  const [codeOpen, setCodeOpen] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [changingCode, setChangingCode] = useState(false);
  const [codeError, setCodeError] = useState("");
  const [addFormOpen, setAddFormOpen] = useState(false);
  const [deviceSectionOpen, setDeviceSectionOpen] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [orgFilter, setOrgFilter] = useState(""); // "" = all institutions
  const [schoolFilter, setSchoolFilter] = useState(""); // "" = all schools
  const [deptFilter, setDeptFilter] = useState(""); // "" = all departments; else a department name
  const [pageSize, setPageSize] = useState(20); // -1 = All
  const IMPORT_TIMEOUT_MS = 200_000; // 200s so backend fallback (120+60s) can complete

  const filteredRows = rows.filter(
    (r: any) =>
      (!search.trim() ||
        [r.EmployeeName, r.EmployeeCode, r.StringCode, r.ShortNo, r.Department, r.Role, r.CurrentShift].some(
          (v: string) => v && String(v).toLowerCase().includes(search.toLowerCase())
        )) &&
      (!orgFilter || String(r.OrganizationId) === orgFilter) &&
      (!schoolFilter || String(r.SchoolId) === schoolFilter) &&
      (!deptFilter || normDept(r.Department) === normDept(deptFilter))
  );
  // Department dropdown: the master list (of the chosen institution) plus any name employees carry that is not in it.
  const deptOptions = (() => {
    const seen = new Map<string, string>();
    departmentsList
      .filter((d) => !orgFilter || String(d.OrganizationId) === orgFilter)
      .forEach((d) => d.DepartmentName && seen.set(normDept(d.DepartmentName), d.DepartmentName));
    rows
      .filter((r: any) => !orgFilter || String(r.OrganizationId) === orgFilter)
      .forEach((r: any) => r.Department && !seen.has(normDept(r.Department)) && seen.set(normDept(r.Department), String(r.Department).trim()));
    return Array.from(seen.values()).sort((a, b) => a.localeCompare(b));
  })();
  const effSize = pageSize === -1 ? filteredRows.length || 1 : pageSize;
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / effSize));
  const currentPage = Math.min(page, totalPages);
  // Sort No (field ShortNo; the office's own order: 1, 2, 10 - numeric) first, blanks keep their place after; same rule as the reports.
  const shortNoKey = (v: unknown): [number, number, string] => {
    const s = String(v ?? "").trim();
    if (!s) return [2, 0, ""];
    return /^\d+$/.test(s) ? [0, Number(s), ""] : [1, 0, s.toLowerCase()];
  };
  const sortedRows = [...filteredRows].sort((a, b) => {
    const [ka, kb] = [shortNoKey(a.ShortNo), shortNoKey(b.ShortNo)];
    return ka[0] - kb[0] || ka[1] - kb[1] || ka[2].localeCompare(kb[2]);
  });
  const paginatedRows = sortedRows.slice((currentPage - 1) * effSize, currentPage * effSize);
  const pageIds: number[] = paginatedRows.map((r: any) => r.EmployeeId);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const toggleSelectPage = () =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allOnPageSelected) pageIds.forEach((id) => next.delete(id));
      else pageIds.forEach((id) => next.add(id));
      return next;
    });

  const load = () =>
    api.getEmployees().then(setRows).catch((e) => {
      // Keep whatever is already on screen — blanking the list on a failed refresh (a slow
      // backend, a dropped connection, an expired session) used to look identical to "no
      // employees", and nothing told the admin why, or that a hard refresh wouldn't help.
      setDeviceOpsStatus("Could not load employees: " + (e instanceof Error ? e.message : "unknown error"));
    });
  const loadDevices = () =>
    api
      .getDevices()
      .then((items) => {
        setDevices(items);
        if (items.length > 0 && !selectedDeviceId) {
          setSelectedDeviceId(String(items[0].DeviceId));
        }
      })
      .catch(() => setDevices([]));
  const loadCategories = () =>
    api.getCategories().then((list: CategoryOption[]) => setCategories(list)).catch(() => setCategories([]));
  const checkBackend = useCallback(() => {
    setBackendChecking(true);
    api.checkBackendHealth().then((ok) => { setBackendOnline(ok); setBackendChecking(false); }).catch(() => { setBackendOnline(false); setBackendChecking(false); });
  }, []);

  const loadMasters = () => {
    api.getOrganizations().then(setOrganizations).catch(() => setOrganizations([]));
    // Campus roles (User Roles) can be given to a portal login like the built-in roles.
    api.getCampusRoles().then((r: any) => setCampusRoleNames((r.roles || []).map((c: any) => c.name))).catch(() => {});
    api.getDepartments().then(setDepartmentsList).catch(() => setDepartmentsList([]));
    api.getEmployeeTypes().then(setEmployeeTypes).catch(() => setEmployeeTypes([]));
    api.getDesignations().then(setDesignationsList).catch(() => setDesignationsList([]));
    api.getSchools().then(setSchools).catch(() => setSchools([]));
  };

  useEffect(() => {
    load();
    loadDevices();
    loadCategories();
    loadMasters();
    api.getShifts().then((l: any[]) => setShifts(l.filter((x) => x.IsActive !== "N"))).catch(() => setShifts([]));
  }, []);

  // Organization is required (no "None"): preselect the first one, the same default the server uses,
  // for a new employee and for older records that were saved without one.
  const defaultOrgId = organizations.length
    ? String([...organizations].sort((a, b) => a.OrganizationId - b.OrganizationId)[0].OrganizationId)
    : "";
  useEffect(() => {
    if ((addFormOpen || editingEmployeeId !== null) && !editForm.OrganizationId && defaultOrgId) {
      setEditForm((f) => (f.OrganizationId ? f : { ...f, OrganizationId: defaultOrgId }));
    }
  }, [addFormOpen, editingEmployeeId, editForm.OrganizationId, defaultOrgId]);

  useEffect(() => {
    if (editingEmployeeId !== null && backendOnline === null && !backendChecking) checkBackend();
  }, [editingEmployeeId, backendOnline, backendChecking, checkBackend]);

  const openAdd = () => {
    setEditingEmployeeId(null);
    setEditForm(blankEdit());
    setForm({ EmployeeCode: "", LoginName: "", LoginPassword: "" });
    setFormError("");
    setDeviceSectionOpen(false);
    setShiftId("");
    setShiftWas("");
    setShiftFrom("");
    setAddFormOpen(true);
  };

  // Give an employee (or several) a shift from a date. Saved as a roster entry; earlier ones end the day before.
  const assignShiftTo = (codes: string[], shift: string, from: string, to?: string) =>
    api.assignShift({ EmployeeCodes: codes, ShiftId: Number(shift), FromDate: from, ToDate: to || null });

  // Optional numeric master ids: send a number, or drop the key when nothing is picked.
  const withIds = (payload: any) => {
    ["CategoryId", "OrganizationId", "EmployeeTypeId", "SchoolId"].forEach((k) => {
      if (payload[k] === "" || payload[k] === undefined) delete payload[k];
      else payload[k] = Number(payload[k]);
    });
    return payload;
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setFormError("");
    const employeeCode = form.EmployeeCode.trim();
    if (!editForm.EmployeeName.trim()) { setFormError("Enter the employee's name."); return; }
    if (!employeeCode) { setFormError("Enter the Face ID (the code the device or camera uses)."); return; }
    if (!editForm.OrganizationId) { setFormError("Choose an organization."); return; }
    if (form.LoginName.trim() && !form.LoginPassword) { setFormError("Enter a password for the portal login, or clear the username."); return; }

    const usedNumericCodes = rows
      .map((row: any) => Number(row.NumericCode))
      .filter((num: number) => Number.isFinite(num) && num > 0);
    const nextNumericCode = usedNumericCodes.length > 0 ? Math.max(...usedNumericCodes) + 1 : 1;
    const numericCode = /^d+$/.test(employeeCode) ? Number(employeeCode) : nextNumericCode;

    // Only send fields that were filled in.
    const filled: any = {};
    HR_FIELDS.forEach((k) => { if (editForm[k] !== "") filled[k] = editForm[k]; });
    const payload = withIds({
      ...filled,
      EmployeeName: editForm.EmployeeName.trim(),
      EmployeeCode: employeeCode,
      StringCode: editForm.StringCode.trim() || employeeCode,
      NumericCode: numericCode,
    });

    setSaving(true);
    try {
      await api.createEmployee(payload);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not add the employee.");
      setSaving(false);
      return;
    }
    let message = `Employee ${editForm.EmployeeName.trim()} added.`;
    if (form.LoginName.trim() && form.LoginPassword) {
      try {
        await api.createUser({
          login_name: form.LoginName.trim(),
          password: form.LoginPassword,
          role_name: editForm.Role || "Employee",
          employee_code: employeeCode,
        });
        message = `Employee ${editForm.EmployeeName.trim()} and portal login created.`;
      } catch (err) {
        message = "Employee created. Portal user failed: " + (err instanceof Error ? err.message : "unknown");
      }
    }
    if (shiftId) {
      try {
        await assignShiftTo([employeeCode], shiftId, shiftFrom || editForm.JoiningDate || todayIso());
      } catch (err) {
        message += " Shift not assigned: " + (err instanceof Error ? err.message : "unknown");
      }
    }
    setDeviceOpsStatus(message);
    setSaving(false);
    cancelEdit();
    load();
  };

  const handleGenerateCredentials = useCallback(() => {
    const { username, password } = generateCredentials();
    setForm((prev) => ({ ...prev, LoginName: username, LoginPassword: password }));
  }, []);

  const startEdit = (row: any) => {
    setAddFormOpen(false);
    setFormError("");
    setEditingEmployeeId(row.EmployeeId);
    setFaceCount(null);
    api.getFaceEnrollments(row.EmployeeCode ?? "").then((r: any[]) => setFaceCount(r.length)).catch(() => setFaceCount(-1));
    setEditingEmployeeCode(row.EmployeeCode ?? "");
    setPortalLoginUsername(row.EmployeeCode ?? "");
    setPortalLoginPassword("");
    setPortalMessage("");
    setBackendOnline(null);
    const next = blankEdit();
    HR_FIELDS.forEach((k) => {
      const v = (row as any)[k];
      (next as any)[k] = v === null || v === undefined ? "" : String(v);
    });
    if (!next.Role) next.Role = "Employee";
    if (!next.CurrentStatus) next.CurrentStatus = "Active";
    if (!next.StringCode) next.StringCode = row.EmployeeCode ?? "";
    setEditForm(next);
    const cur = row.CurrentShiftId ? String(row.CurrentShiftId) : "";
    setShiftId(cur);
    setShiftWas(cur);
    setShiftFrom(todayIso());
  };

  const cancelEdit = () => {
    setAddFormOpen(false);
    setFormError("");
    setEditingEmployeeId(null);
    setEditingEmployeeCode("");
    setPortalLoginUsername("");
    setPortalLoginPassword("");
    setPortalMessage("");
    setEditForm(blankEdit());
  };

  const handleGeneratePortalCredentials = useCallback(() => {
    const { username, password } = generateCredentials();
    setPortalLoginUsername(username);
    setPortalLoginPassword(password);
    setPortalMessage("");
  }, []);

  const handleCreatePortalLogin = async () => {
    const un = portalLoginUsername.trim();
    const pw = portalLoginPassword;
    setPortalMessage("");
    if (!un) {
      setPortalMessage("Enter a portal username.");
      return;
    }
    if (!pw) {
      setPortalMessage("Enter a password.");
      return;
    }
    try {
      await api.createUser({ login_name: un, password: pw, role_name: editForm.Role || "Employee", employee_code: editingEmployeeCode });
      setPortalMessage("Portal login created. Share the username and password with the employee.");
      setPortalLoginPassword("");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg === "Failed to fetch" || (msg && msg.toLowerCase().includes("fetch"))) {
        setPortalMessage("Cannot reach the server. Ensure the backend is running (e.g. http://localhost:8000).");
      } else {
        setPortalMessage(msg);
      }
    }
  };

  const handleResetPortalPassword = async () => {
    const un = portalLoginUsername.trim();
    const pw = portalLoginPassword;
    setPortalMessage("");
    if (!un) {
      setPortalMessage("Enter the employee's portal username.");
      return;
    }
    if (!pw) {
      setPortalMessage("Enter the new password.");
      return;
    }
    try {
      await api.resetPassword({ login_name: un, new_password: pw });
      setPortalMessage("Password reset. Share the new password with the employee.");
      setPortalLoginPassword("");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg === "Failed to fetch" || (msg && msg.toLowerCase().includes("fetch"))) {
        setPortalMessage("Cannot reach the server. Ensure the backend is running (e.g. http://localhost:8000).");
      } else {
        setPortalMessage(msg);
      }
    }
  };

  const [copiedField, setCopiedField] = useState<"portal-user" | "portal-pw" | "add-user" | "add-pw" | null>(null);
  const copyToClipboard = useCallback((text: string, field: "portal-user" | "portal-pw" | "add-user" | "add-pw") => {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      setCopiedField(field);
      window.setTimeout(() => setCopiedField(null), 2000);
    });
  }, []);

  const saveEdit = async (event: FormEvent) => {
    event.preventDefault();
    if (editingEmployeeId === null) return;
    setFormError("");
    if (!editForm.EmployeeName.trim()) { setFormError("Enter the employee's name."); return; }
    if (isExiting && !editForm.LastWorkingDay) { setFormError(`Enter the last working day for a ${editForm.CurrentStatus} employee.`); return; }
    setSaving(true);
    try {
      await api.updateEmployee(editingEmployeeId, withIds({ ...editForm }));
      if (shiftId && shiftId !== shiftWas) {
        try {
          await assignShiftTo([editingEmployeeCode], shiftId, shiftFrom || todayIso());
          setDeviceOpsStatus("Profile saved and shift assigned.");
        } catch (err) {
          setDeviceOpsStatus("Profile saved, but the shift was not assigned: " + (err instanceof Error ? err.message : "unknown"));
        }
      }
      cancelEdit();
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not save the profile.");
    } finally {
      setSaving(false);
    }
  };

  // Field renderers for the profile editor (close over editForm / setEditForm).
  const efSet = (k: keyof EditForm, v: string) => setEditForm({ ...editForm, [k]: v });
  const lbl = (label: string) => (label.endsWith(" *") ? <>{label.slice(0, -2)} <Req /></> : label);
  const Field = (label: string, k: keyof EditForm, opts: { type?: string; full?: boolean; ph?: string } = {}) => (
    <div className={"field" + (opts.full ? " field-full" : "")} key={k}>
      <label>{lbl(label)}</label>
      <input type={opts.type || "text"} value={editForm[k]} placeholder={opts.ph || ""}
        required={k === "EmployeeName"} onChange={(e) => efSet(k, e.target.value)} />
    </div>
  );
  const AreaField = (label: string, k: keyof EditForm) => (
    <div className="field field-full" key={k}>
      <label>{label}</label>
      <textarea rows={2} value={editForm[k]} onChange={(e) => efSet(k, e.target.value)} />
    </div>
  );
  const SelectField = (label: string, k: keyof EditForm, options: { value: string; label: string }[], onPick?: (v: string) => void) => (
    <div className="field" key={k}>
      <label>{label}</label>
      <select value={editForm[k]} onChange={(e) => (onPick ? onPick(e.target.value) : efSet(k, e.target.value))}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
  // Dropdown options from a master list; keeps an existing value that is no longer in the list
  // (e.g. legacy free-text data) so opening a profile never silently blanks it.
  const listOptions = (names: string[], current: string, noneLabel = "— None —") => {
    const uniq = Array.from(new Set(names.filter(Boolean)));
    if (current && !uniq.includes(current)) uniq.unshift(current);
    return [{ value: "", label: noneLabel }, ...uniq.map((n) => ({ value: n, label: n }))];
  };
  const roleOptions = (current: string) => {
    // A campus login hands out only its own campus role (or Employee); an Admin can give any role.
    const opts = campus ? ["Employee", ...campusRoleNames] : [...ROLE_OPTIONS, ...campusRoleNames];
    if (current && !opts.includes(current)) opts.unshift(current);
    return [{ value: "", label: "— Select —" }, ...opts.map((n) => ({ value: n, label: ROLE_LABEL[n] ?? n }))];
  };
  const deptNames = departmentsList.map((d) => d.DepartmentName);
  const designationNames = designationsList.map((d) => d.DesignationName);
  const todayIso = () => new Date().toISOString().slice(0, 10);
  // Picking an exit status suggests today as the last working day; going back to Active clears the exit details.
  const pickStatus = (st: string) => {
    const leaving = ["Inactive", "Resigned", "Terminated"].includes(st);
    setEditForm({
      ...editForm,
      CurrentStatus: st,
      LastWorkingDay: leaving ? (editForm.LastWorkingDay || todayIso()) : "",
      ReasonForLeaving: leaving ? editForm.ReasonForLeaving : "",
    });
  };
  const isExiting = ["Inactive", "Resigned", "Terminated"].includes(editForm.CurrentStatus);

  const importFromDevice = async () => {
    if (!selectedDeviceId) {
      setDeviceOpsStatus("Please select a device for import.");
      return;
    }
    if (importing) return;
    setImporting(true);
    setDeviceOpsStatus("Importing employees and biometrics from device… This may take 1–2 minutes when Face/Finger are enabled.");
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), IMPORT_TIMEOUT_MS);
    try {
      const result = await api.importEmployeesFromDevice(
        Number(selectedDeviceId),
        { ...syncOptions },
        { signal: controller.signal }
      );
      window.clearTimeout(timeoutId);
      setDeviceOpsStatus(
        `Import completed. Device users: ${result.total_device_users}, New: ${result.imported}, Updated: ${result.updated}, Bio: ${result.biometric_upserts}, Photos: ${result.photos_upserts}`
      );
      await load();
    } catch (err) {
      window.clearTimeout(timeoutId);
      const message = (err as Error).message;
      if (err instanceof Error && err.name === "AbortError") {
        setDeviceOpsStatus("Import timed out (over 3 minutes). Try unchecking Face and Finger for a faster import of names and codes only.");
      } else if (message === "Failed to fetch" || message.includes("fetch")) {
        setDeviceOpsStatus(
          "Import failed: Cannot reach the server. Start the backend on port 8000 (e.g. from Aveon/backend: uvicorn app.main:app --reload --port 8000). Check http://localhost:8000/health. Frontend .env must have VITE_API_BASE_URL=http://localhost:8000/api/v1."
        );
      } else {
        setDeviceOpsStatus(`Import failed: ${message}`);
      }
    } finally {
      setImporting(false);
    }
  };

  const syncToDevice = async () => {
    if (!selectedDeviceId) {
      setDeviceOpsStatus("Please select a device for sync.");
      return;
    }
    setDeviceOpsStatus("Queueing employee sync to device...");
    setSyncing(true);
    try {
      const result = await api.syncEmployeesToDevice(Number(selectedDeviceId), {
        employee_codes: [],
        queue_only: true,
        ...syncOptions,
      });
      setDeviceOpsStatus(`Sync queued. Users: ${result.synced_users}, Commands queued: ${result.queued_commands}`);
    } catch (err) {
      const msg = (err as Error).message;
      if (msg === "Failed to fetch" || msg.includes("fetch")) {
        setDeviceOpsStatus(
          "Sync failed: Cannot reach the server. Start the backend on port 8000 (e.g. from Aveon/backend: uvicorn app.main:app --reload --port 8000). Check http://localhost:8000/health. Frontend .env must have VITE_API_BASE_URL=http://localhost:8000/api/v1."
        );
      } else {
        setDeviceOpsStatus(`Sync failed: ${msg}`);
      }
    } finally {
      setSyncing(false);
    }
  };

  // ---- Excel import ----
  const buildMapping = (colToField: Record<number, string>, headerRow: number) => {
    const columns: Record<string, number> = {};
    // Later columns win if two point at the same field.
    Object.entries(colToField).forEach(([idx, field]) => {
      if (field) columns[field] = Number(idx);
    });
    return { header_row: headerRow, columns };
  };

  const runPreview = async (file: File, colToField: Record<number, string>, headerRow: number) => {
    setXlBusy(true);
    setXlError("");
    try {
      const res = await api.importPreview(file, buildMapping(colToField, headerRow));
      setXlPreview(res);
    } catch (err) {
      setXlError(err instanceof Error ? err.message : "Could not read the file.");
      setXlPreview(null);
    } finally {
      setXlBusy(false);
    }
  };

  const askDelete = (row: any) => {
    setDelTarget(row); setDelPreview(null); setDelReaders(true);
    api.getEmployeeDeletePreview(row.EmployeeId).then(setDelPreview).catch((e) => setDelPreview({ error: e instanceof Error ? e.message : "Could not load" }));
  };
  const confirmDelete = async () => {
    if (!delTarget) return;
    setDeleting(true);
    try {
      const r = await api.deleteEmployee(delTarget.EmployeeId, delReaders);
      setDeviceOpsStatus(r?.message || "Employee deleted.");
      setDelTarget(null);
      load();
    } catch (e) {
      setDeviceOpsStatus("Could not delete: " + (e instanceof Error ? e.message : "unknown error"));
    } finally {
      setDeleting(false);
    }
  };
  const openDups = () => {
    setDupOpen(true); setDups(null);
    api.getStudentDuplicates().then(setDups).catch((e) => { setDups([]); setDeviceOpsStatus("Could not check: " + (e instanceof Error ? e.message : "unknown")); });
  };
  const confirmDups = async () => {
    if (!dups?.length) return;
    setDupBusy(true);
    try {
      const r = await api.deleteStudentDuplicates(dups.map((d: any) => d.EmployeeCode));
      setDeviceOpsStatus(r?.message || "Done.");
      setDupOpen(false);
      load();
    } catch (e) {
      setDeviceOpsStatus("Could not clean up: " + (e instanceof Error ? e.message : "unknown error"));
    } finally {
      setDupBusy(false);
    }
  };

  const openImport = () => {
    setXlOpen(true);
    setXlFile(null);
    setXlColumns([]);
    setXlColToField({});
    setXlPreview(null);
    setXlError("");
    setXlHeaderRow(1);
    setXlFields([]);
  };

  const closeImport = () => {
    setXlOpen(false);
    setXlFile(null);
    setXlColumns([]);
    setXlColToField({});
    setXlPreview(null);
    setXlError("");
  };

  const onImportFileChosen = async (file: File | null) => {
    if (!file) return;
    setXlFile(file);
    setXlPreview(null);
    setXlColumns([]);
    setXlColToField({});
    setXlBusy(true);
    setXlError("");
    try {
      const res = await api.importInspect(file);
      setXlColumns(res.columns || []);
      setXlFields(res.fields || Object.keys(IMPORT_FIELD_LABELS));
      setXlHeaderRow(res.header_row || 1);
      // Invert guessed_mapping (field -> index) into columnIndex -> field.
      const colToField: Record<number, string> = {};
      Object.entries(res.guessed_mapping || {}).forEach(([field, idx]) => {
        colToField[Number(idx)] = field;
      });
      setXlColToField(colToField);
      await runPreview(file, colToField, res.header_row || 1);
    } catch (err) {
      setXlError(err instanceof Error ? err.message : "Could not read the file.");
    } finally {
      setXlBusy(false);
    }
  };

  const setColMapping = (colIndex: number, field: string) => {
    // A field maps to one column: clear it from any other column first.
    const next: Record<number, string> = {};
    Object.entries(xlColToField).forEach(([idx, f]) => {
      if (Number(idx) !== colIndex && f !== field) next[Number(idx)] = f;
    });
    if (field) next[colIndex] = field;
    setXlColToField(next);
    if (xlFile) runPreview(xlFile, next, xlHeaderRow);
  };

  const changeHeaderRow = (row: number) => {
    setXlHeaderRow(row);
    if (xlFile) runPreview(xlFile, xlColToField, row);
  };

  const doImportCommit = async () => {
    if (!xlFile) return;
    setXlBusy(true);
    setXlError("");
    try {
      const res = await api.importCommit(xlFile, buildMapping(xlColToField, xlHeaderRow));
      const s = res.summary || {};
      const mc = res.masters_created || {};
      const mcParts = [
        mc.organizations?.length ? `${mc.organizations.length} org` : "",
        mc.departments?.length ? `${mc.departments.length} dept` : "",
        mc.designations?.length ? `${mc.designations.length} designation` : "",
        mc.employee_types?.length ? `${mc.employee_types.length} type` : "",
      ].filter(Boolean);
      setDeviceOpsStatus(
        `Import complete. Added: ${s.created ?? 0}, Updated: ${s.updated ?? 0}, Skipped: ${s.skipped ?? 0}, Errors: ${s.errors ?? 0}.` +
          (mcParts.length ? ` New masters: ${mcParts.join(", ")}.` : "")
      );
      closeImport();
      await load();
      loadMasters();
    } catch (err) {
      setXlError(err instanceof Error ? err.message : "Import failed.");
    } finally {
      setXlBusy(false);
    }
  };

  // ---- Bulk move ----
  const toggleSelect = (id: number) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const clearSelection = () => setSelectedIds(new Set());
  const openMove = () => { setMoveOrg(""); setMoveDept(""); setMoveSchool(""); setMoveOpen(true); };
  const doMove = async () => {
    if (selectedIds.size === 0 || (!moveOrg && !moveDept && !moveSchool)) return;
    setMoving(true);
    try {
      const payload: { employee_ids: number[]; OrganizationId?: number; Department?: string; SchoolId?: number } = {
        employee_ids: Array.from(selectedIds),
      };
      if (moveOrg) payload.OrganizationId = Number(moveOrg);
      if (moveDept) payload.Department = moveDept;
      if (moveSchool) payload.SchoolId = Number(moveSchool);
      const res = await api.moveEmployees(payload);
      setDeviceOpsStatus(`Moved ${res.moved} employee${res.moved === 1 ? "" : "s"}.`);
      setMoveOpen(false);
      clearSelection();
      await load();
      loadMasters();
    } catch (err) {
      setDeviceOpsStatus(`Move failed: ${err instanceof Error ? err.message : "unknown"}`);
    } finally {
      setMoving(false);
    }
  };

  const openAssign = () => { setAssignShiftId(""); setAssignFrom(todayIso()); setAssignTo(""); setAssignOpen(true); };
  const doAssign = async () => {
    if (selectedIds.size === 0 || !assignShiftId || !assignFrom) return;
    const codes = rows.filter((r: any) => selectedIds.has(r.EmployeeId)).map((r: any) => r.EmployeeCode);
    setAssigning(true);
    try {
      const res = await assignShiftTo(codes, assignShiftId, assignFrom, assignTo);
      setDeviceOpsStatus(`Shift assigned to ${res.assigned} employee${res.assigned === 1 ? "" : "s"}, from ${assignFrom}.`);
      setAssignOpen(false);
      clearSelection();
      await load();
    } catch (err) {
      setDeviceOpsStatus(`Assign shift failed: ${err instanceof Error ? err.message : "unknown"}`);
    } finally {
      setAssigning(false);
    }
  };

  // ---- Change code (edit dialog) ----
  const openChangeCode = () => { setNewCode(""); setCodeError(""); setCodeOpen(true); };
  const doChangeCode = async () => {
    if (editingEmployeeId === null) return;
    const code = newCode.trim();
    if (!code) { setCodeError("Enter the new code."); return; }
    if (code === editingEmployeeCode) { setCodeError("That is already the current code."); return; }
    setChangingCode(true);
    setCodeError("");
    try {
      await api.changeEmployeeCode(editingEmployeeId, code);
      setEditingEmployeeCode(code);
      setCodeOpen(false);
      setDeviceOpsStatus(`Face ID changed to ${code}. All records, punches and face enrollment were re-pointed.`);
      load();
    } catch (err) {
      setCodeError(err instanceof Error ? err.message : "Could not change the code.");
    } finally {
      setChangingCode(false);
    }
  };

  const CopyIcon = () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
  );
  const LockIcon = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
  );
  const SearchIcon = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
  );

  const sectionHeader = (title: string, open: boolean, onToggle: () => void) => (
    <button type="button" onClick={onToggle} style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 14, color: "var(--text)" }}>
      {title}
      <span style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
    </button>
  );

  return (
    <div className="employee-mgmt-page">
      <header className="employee-mgmt-header">
        <h2>Employee Management</h2>
        <div className="employee-mgmt-header-actions">
          <button type="button" className="btn-outline-gray" onClick={() => setShowHelp((v) => !v)} aria-label="Help">
            {showHelp ? "Hide help" : "What is ID / Code?"}
          </button>
          {!campus && <>
            <button type="button" className="btn-outline-reports" onClick={openImport}>Import from Excel</button>
            <button type="button" className="btn-outline-reports" onClick={openDups} title="Students a shared reader created as staff">Clean up student records</button>
          </>}
          <button type="button" className="btn btn-primary-purple" onClick={openAdd}>+ Add Employee</button>
        </div>
      </header>

      {showHelp && (
        <div className="employee-mgmt-info-banner" role="status">
          <span className="info-icon" aria-hidden>i</span>
          <span><strong>Employee Code</strong> = the HR / staff number shown in lists and reports. <strong>Face ID</strong> = the code the device or camera uses to recognise the person (it links punches, face data and leaves).</span>
        </div>
      )}

      {importing ? (
        <LoadingNote
          message="Importing employees and biometrics from the reader…"
          hint="This can take 1–2 minutes when Face / Finger are included. Keep this page open."
          bar
        />
      ) : syncing ? (
        <LoadingNote
          message="Queuing employees for the reader…"
          hint="The reader receives them on its next check-in, usually within a minute."
        />
      ) : deviceOpsStatus && (
        <div className="employee-mgmt-status-msg">{deviceOpsStatus}</div>
      )}

      <div style={{ marginBottom: 16 }}>
        {sectionHeader(deviceSectionOpen ? "Import / sync from device" : "Import / sync from device (click to expand)", deviceSectionOpen, () => setDeviceSectionOpen((o) => !o))}
        {deviceSectionOpen && (
          <div style={{ marginTop: 8, padding: 14, background: "var(--surface)", border: "1px solid var(--border)", borderTop: "none", borderRadius: "0 0 8px 8px" }}>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginBottom: 8 }}>
              <select value={selectedDeviceId} onChange={(e) => setSelectedDeviceId(e.target.value)} disabled={importing} style={{ minWidth: 200 }}>
                {devices.length === 0 && <option value="">No devices</option>}
                {devices.map((d) => <option key={d.DeviceId} value={d.DeviceId}>{d.DeviceName} ({d.DeviceIPAddress || "No IP"})</option>)}
              </select>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}><input type="checkbox" checked={syncOptions.include_face} onChange={(e) => setSyncOptions({ ...syncOptions, include_face: e.target.checked })} disabled={importing} />Face</label>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}><input type="checkbox" checked={syncOptions.include_finger} onChange={(e) => setSyncOptions({ ...syncOptions, include_finger: e.target.checked })} disabled={importing} />Finger</label>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}><input type="checkbox" checked={syncOptions.include_card} onChange={(e) => setSyncOptions({ ...syncOptions, include_card: e.target.checked })} disabled={importing} />RFID/Card</label>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}><input type="checkbox" checked={syncOptions.include_photo} onChange={(e) => setSyncOptions({ ...syncOptions, include_photo: e.target.checked })} disabled={importing} />Photo</label>
              <button type="button" onClick={importFromDevice} disabled={importing}>{importing ? <><BtnSpinner />Importing…</> : "Import From Device"}</button>
              <button type="button" onClick={syncToDevice} disabled={importing || syncing}>{syncing ? <><BtnSpinner />Queuing…</> : "Update Software To Device"}</button>
            </div>
            <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>With Face/Finger checked, import can take 1–2 minutes. Uncheck for quick names/codes only.</p>
          </div>
        )}
      </div>

      {(editingEmployeeId !== null || addFormOpen) && (
        <div className="modal-overlay" onClick={cancelEdit}>
        <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="emp-edit-card">
          <div className="emp-edit-head">
            <div className="emp-edit-title">
              <span className="emp-avatar" aria-hidden>{addFormOpen && !editForm.EmployeeName.trim() ? "+" : initialsOf(editForm.EmployeeName)}</span>
              <div>
                <h3>{addFormOpen ? "Add new employee" : "Edit employee profile"}</h3>
                <span className="emp-edit-sub">
                  {addFormOpen
                    ? "Only name and Face ID are required. Fill in the rest now or later."
                    : <>{editForm.EmployeeName || "—"} · Face ID {editingEmployeeCode}</>}
                </span>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              {!addFormOpen && <button type="button" className="btn-outline-reports" onClick={openChangeCode}>Change Face ID</button>}
              {!addFormOpen && <span className={"badge " + (isExiting ? "badge-red" : "badge-green")}>{editForm.CurrentStatus || "Active"}</span>}
              <button type="button" className="modal-close" onClick={cancelEdit} aria-label="Close">×</button>
            </div>
          </div>

          <div className="emp-edit-scroll">
          <form onSubmit={addFormOpen ? submit : saveEdit}>
            {formError && <div className="emp-error" role="alert">{formError}</div>}
            <section className="emp-section">
              <SectionHead icon={Icons.employees} title="Employment" desc="Where they work and their current status" />
              <div className="emp-grid">
                {Field("Name *", "EmployeeName", { ph: "Full name" })}
                <div className="field" key="StringCode">
                  <label htmlFor="emp-hr-code">Employee Code</label>
                  <input id="emp-hr-code" value={editForm.StringCode} placeholder={addFormOpen ? "e.g. CSC15T44 (optional)" : ""} autoComplete="off"
                    onChange={(e) => efSet("StringCode", e.target.value)} />
                  <span className="field-hint">The HR / staff number shown in lists and reports. Leave blank to use the Face ID.</span>
                </div>
                {addFormOpen && (
                  <div className="field" key="EmployeeCode">
                    <label htmlFor="emp-code">Face ID <Req /></label>
                    <input id="emp-code" value={form.EmployeeCode} placeholder="e.g. 202445" required
                      onChange={(e) => setForm({ ...form, EmployeeCode: e.target.value })} />
                    <span className="field-hint">The ID the device or camera uses to recognise this person. It must match the ID on the device. Change it later with the “Change Face ID” button.</span>
                  </div>
                )}
                {!addFormOpen && (
                  <div className="field" key="EmployeeCodeRO">
                    <label htmlFor="emp-code-ro">Face ID</label>
                    <input id="emp-code-ro" value={editingEmployeeCode} disabled readOnly />
                    <span className="field-hint">The ID the device or camera uses to recognise this person. Use the “Change Face ID” button above to change it.</span>
                  </div>
                )}
                <div className="field" key="ShortNo">
                  <label htmlFor="emp-short-no">Sort No</label>
                  <input id="emp-short-no" value={editForm.ShortNo} maxLength={20} placeholder="e.g. 12 (optional)" autoComplete="off"
                    onChange={(e) => efSet("ShortNo", e.target.value)} />
                  <span className="field-hint">The office's own order: the employee list and reports are sorted by it (1, 2, 10 …). Optional; it is not the Face ID and is not sent to devices.</span>
                </div>
                {SelectField("Organization *", "OrganizationId", organizations.map((o) => ({ value: String(o.OrganizationId), label: o.OrgName })), (v) => setEditForm({ ...editForm, OrganizationId: v, Department: "" }))}
                {SelectField("School", "SchoolId", [{ value: "", label: "— None —" }, ...schools.map((x) => ({ value: String(x.SchoolId), label: x.SchoolName }))])}
                {SelectField("Department", "Department", listOptions(
                  departmentsList.filter((d) => !editForm.OrganizationId || d.OrganizationId === Number(editForm.OrganizationId)).map((d) => d.DepartmentName),
                  editForm.Department))}
                {SelectField("Designation", "Designation", listOptions(designationNames, editForm.Designation))}
                {SelectField("Employee type", "EmployeeTypeId", [{ value: "", label: "— None —" }, ...employeeTypes.map((t) => ({ value: String(t.EmployeeTypeId), label: t.TypeName }))])}
                {SelectField("Role", "Role", roleOptions(editForm.Role))}
                {SelectField("Category", "CategoryId", [{ value: "", label: "— None —" }, ...categories.map((c) => ({ value: String(c.CategoryId), label: c.CategoryName }))])}
                {Field("Joining Date", "JoiningDate", { type: "date" })}
                <div className="field">
                  <label htmlFor="emp-shift">Shift</label>
                  <select id="emp-shift" value={shiftId} onChange={(e) => setShiftId(e.target.value)}>
                    <option value="">— Not assigned —</option>
                    {shifts.map((x) => <option key={x.ShiftId} value={x.ShiftId}>{x.ShiftName}{x.StartTime ? ` (${String(x.StartTime).slice(0, 5)}–${String(x.EndTime).slice(0, 5)})` : ""}</option>)}
                  </select>
                  <span className="field-hint">Working hours used for late / early / overtime. Manage shifts under Configuration → Shifts.</span>
                </div>
                {shiftId && shiftId !== shiftWas && (
                  <div className="field">
                    <label htmlFor="emp-shift-from">Shift starts on</label>
                    <input id="emp-shift-from" type="date" value={shiftFrom} onChange={(e) => setShiftFrom(e.target.value)} />
                    <span className="field-hint">{addFormOpen ? "Blank = the joining date (or today). " : ""}Their earlier shift ends the day before.</span>
                  </div>
                )}
                <div className="field field-span-2">
                  <label>Current status</label>
                  <div className="seg" role="group" aria-label="Current status">
                    {["Active", "Inactive", "Resigned", ...(editForm.CurrentStatus === "Terminated" ? ["Terminated"] : [])].map((s) => (
                      <button key={s} type="button" className={editForm.CurrentStatus === s ? "on" : ""}
                        aria-pressed={editForm.CurrentStatus === s} onClick={() => pickStatus(s)}>{s}</button>
                    ))}
                  </div>
                </div>
                {isExiting && (
                  <div className="field field-span-2 exit-date">
                    <label htmlFor="emp-lwd">Last working day <Req /></label>
                    <input id="emp-lwd" type="date" value={editForm.LastWorkingDay} required
                      onChange={(e) => efSet("LastWorkingDay", e.target.value)} />
                    <span className="field-hint">
                      Attendance counts up to and including this day. From the next day this employee is {editForm.CurrentStatus}
                      and is no longer marked absent, is left out of the employee count, and their portal login is blocked.
                    </span>
                  </div>
                )}
              </div>
            </section>

            <section className="emp-section">
              <SectionHead icon={Icons.user} title="Personal" desc="Used for records and emergencies" />
              <div className="emp-grid">
                {Field("Date of Birth", "DateOfBirth", { type: "date" })}
                {Field("Parent / Spouse Name", "GuardianName")}
                {SelectField("Marital Status", "MaritalStatus", [{ value: "", label: "—" }, ...["Single", "Married", "Other"].map((s) => ({ value: s, label: s }))])}
                {Field("Blood Group", "BloodGroup", { ph: "e.g. O+" })}
                {AreaField("Address", "Address")}
              </div>
            </section>

            <section className="emp-section">
              <SectionHead icon={Icons.bell} title="Contact" desc="Phone numbers and email" />
              <div className="emp-grid">
                {Field("Contact No", "ContactNo", { type: "tel" })}
                {Field("Official No", "OfficialNo", { type: "tel" })}
                {Field("Emergency No", "EmergencyNo", { type: "tel" })}
                {Field("Personal Email", "PersonalEmail", { type: "email" })}
                {Field("Official Email / ID", "OfficialEmail", { type: "email" })}
              </div>
            </section>

            <section className="emp-section">
              <SectionHead icon={Icons.document} title="Statutory & payroll" desc="Government IDs and salary" />
              <div className="emp-grid">
                {Field("Aadhar No", "AadharNo")}
                {Field("PAN No", "PanNo")}
                {Field("UAN", "UAN")}
                {Field("Salary", "Salary", { ph: "monthly / annual" })}
              </div>
            </section>

            <section className="emp-section">
              <SectionHead icon={Icons.enrollment} title="Card & face" desc="Extra ways this person can be identified at a device" />
              <div className="emp-grid">
                <div className="field">
                  <label htmlFor="emp-rfid">RFID card number</label>
                  <input id="emp-rfid" value={editForm.EmployeeRFIDNumber} placeholder="Optional" autoComplete="off"
                    onChange={(e) => efSet("EmployeeRFIDNumber", e.target.value)} />
                  <span className="field-hint">Only if they also punch with a card. It is sent to devices when you sync.</span>
                </div>
                <div className="field field-span-2">
                  <label>Face recognition</label>
                  {addFormOpen ? (
                    <div className="face-status is-neutral">
                      <span className="face-status-text">Enroll the face after saving, from the Face Attendance page.</span>
                    </div>
                  ) : faceCount === null ? (
                    <div className="face-status is-neutral"><span className="face-status-text">Checking…</span></div>
                  ) : faceCount < 0 ? (
                    <div className="face-status is-neutral"><span className="face-status-text">Could not check face enrollment right now.</span></div>
                  ) : faceCount === 0 ? (
                    <div className="face-status is-warn">
                      <span className="face-status-text"><strong>Not enrolled yet.</strong> The camera cannot recognise this person.</span>
                      <Link to="/face" className="btn btn-outline-reports">Enroll face</Link>
                    </div>
                  ) : (
                    <div className="face-status is-ok">
                      <span className="face-status-text"><strong>Enrolled.</strong> {faceCount} face sample{faceCount === 1 ? "" : "s"} on record.</span>
                      <Link to="/face" className="btn btn-outline-reports">Add samples</Link>
                    </div>
                  )}
                </div>
              </div>
            </section>

            {isExiting && (
              <section className="emp-section emp-section-exit">
                <SectionHead icon={Icons.logout} title="Reason for leaving" desc="Optional note kept on the record" />
                <div className="emp-grid">
                  {AreaField("Reason", "ReasonForLeaving")}
                </div>
              </section>
            )}

            {addFormOpen && (
              <section className="emp-section">
                <SectionHead icon={Icons.roles} title="Portal login" desc="Optional. Lets this person sign in to the ESS portal with the role chosen above." />
                <div className="emp-grid">
                  <div className="field">
                    <label htmlFor="add-login">Username</label>
                    <div className="input-with-button">
                      <input id="add-login" value={form.LoginName} placeholder="e.g. employee code or email" autoComplete="off"
                        onChange={(e) => setForm({ ...form, LoginName: e.target.value })} />
                      <button type="button" className="btn-outline-reports" onClick={() => copyToClipboard(form.LoginName, "add-user")} disabled={!form.LoginName}>
                        {copiedField === "add-user" ? "Copied" : "Copy"}
                      </button>
                    </div>
                  </div>
                  <div className="field">
                    <label htmlFor="add-pass">Password</label>
                    <div className="input-with-button">
                      <input id="add-pass" type="text" value={form.LoginPassword} placeholder="Set a password" autoComplete="new-password"
                        onChange={(e) => setForm({ ...form, LoginPassword: e.target.value })} />
                      <button type="button" className="btn-outline-reports" onClick={() => copyToClipboard(form.LoginPassword, "add-pw")} disabled={!form.LoginPassword}>
                        {copiedField === "add-pw" ? "Copied" : "Copy"}
                      </button>
                    </div>
                  </div>
                  <div className="field">
                    <label>&nbsp;</label>
                    <button type="button" className="btn btn-outline-reports" onClick={handleGenerateCredentials}>Generate credentials</button>
                  </div>
                </div>
              </section>
            )}

            <div className="emp-edit-actions">
              <button type="button" className="btn btn-outline-reports" onClick={cancelEdit}>Cancel</button>
              <button type="submit" className="btn btn-primary-purple" disabled={saving}>
                {saving ? "Saving…" : addFormOpen ? "Add employee" : "Save changes"}
              </button>
            </div>
          </form>
          <div className="emp-portal" hidden={addFormOpen}>
            <h4 style={{ margin: "0 0 10px", fontSize: 14, color: "var(--text-muted)" }}>Portal login (for ESS / dashboard)</h4>
            {backendOnline === false && (
              <div style={{ marginBottom: 10, padding: 10, background: "rgba(220,38,38,0.08)", borderRadius: 8, border: "1px solid rgba(220,38,38,0.3)" }}>
                <strong style={{ color: "var(--danger, #dc2626)" }}>Backend is offline.</strong> Create portal login and Reset password will not work until the API server is running.
                <div style={{ marginTop: 8, fontSize: 12 }}>
                  From folder <code style={{ background: "var(--surface)", padding: "2px 6px", borderRadius: 4 }}>Aveon/backend</code> run <code>run.bat</code> or: <code>python -m uvicorn app.main:app --reload --port 8000</code>
                </div>
                <div style={{ marginTop: 8 }}>
                  <a href={getBackendBaseUrl() + "/health"} target="_blank" rel="noreferrer" style={{ marginRight: 8 }}>Open {getBackendBaseUrl()}/health</a>
                  <button type="button" onClick={checkBackend} disabled={backendChecking}>{backendChecking ? "Checking…" : "Recheck connection"}</button>
                </div>
              </div>
            )}
            <p style={{ margin: "0 0 10px", fontSize: 12, color: "var(--text-muted)" }}>Create a new login for this employee or reset password for an existing portal user.</p>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 10 }}>
              <div>
                <label style={{ display: "block", marginBottom: 4, fontSize: 12, color: "var(--text-muted)" }}>Portal username</label>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <input value={portalLoginUsername} onChange={(e) => { setPortalLoginUsername(e.target.value); setPortalMessage(""); }} placeholder="e.g. employee code or email" style={{ width: 180 }} />
                  <button type="button" onClick={() => copyToClipboard(portalLoginUsername, "portal-user")} disabled={!portalLoginUsername} title="Copy username" style={{ padding: "6px 10px" }}>{copiedField === "portal-user" ? "Copied!" : "Copy"}</button>
                </div>
              </div>
              <div>
                <label style={{ display: "block", marginBottom: 4, fontSize: 12, color: "var(--text-muted)" }}>Password</label>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <input type="password" value={portalLoginPassword} onChange={(e) => { setPortalLoginPassword(e.target.value); setPortalMessage(""); }} placeholder="New or current password" style={{ width: 160 }} />
                  <button type="button" onClick={() => copyToClipboard(portalLoginPassword, "portal-pw")} disabled={!portalLoginPassword} title="Copy password" style={{ padding: "6px 10px" }}>{copiedField === "portal-pw" ? "Copied!" : "Copy"}</button>
                </div>
              </div>
              <button type="button" onClick={handleGeneratePortalCredentials}>Generate username &amp; password</button>
              <button type="button" onClick={handleCreatePortalLogin}>Create portal login</button>
              <button type="button" onClick={handleResetPortalPassword}>Reset password</button>
            </div>
            {portalMessage && <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--text)" }}>{portalMessage}</p>}
          </div>
          </div>
        </div>
        </div>
        </div>
      )}

      {delTarget && (
        <div className="modal-overlay" onClick={() => !deleting && setDelTarget(null)} style={{ zIndex: 60 }}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" style={{ maxWidth: 520 }}>
            <div className="emp-edit-head">
              <div><h3>Delete {delTarget.EmployeeName}</h3><span className="emp-edit-sub">Employee Code {delTarget.StringCode || delTarget.EmployeeCode} · Face ID {delTarget.EmployeeCode}</span></div>
              <button type="button" className="modal-close" onClick={() => setDelTarget(null)} aria-label="Close">×</button>
            </div>
            <div style={{ padding: "4px 18px 18px" }}>
              {!delPreview ? <p className="sub">Checking what is attached…</p> : delPreview.error ? <p className="note-err">{delPreview.error}</p> : (
                <>
                  <p className="sub">This removes the person and everything attached here:
                    {" "}{[["templates", "face / fingerprint template"], ["photos", "photo"], ["rosters", "shift roster entry"], ["leave_requests", "leave request"],
                          ["leave_balances", "leave balance"], ["manual_entries", "manual entry"], ["processed_days", "processed attendance day"]]
                      .filter(([k]) => delPreview[k] > 0).map(([k, l]) => `${delPreview[k]} ${l}${delPreview[k] > 1 ? "s" : ""}`).join(", ") || "nothing else is attached"}.
                    {" "}Their punches are kept for audit.{delPreview.portal_login ? " Their portal login is unlinked." : ""}</p>
                  <label className="field-check" style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 10 }}>
                    <input type="checkbox" checked={delReaders} onChange={(e) => setDelReaders(e.target.checked)} />
                    <span>Also remove from the readers{delPreview.readers?.length ? ` (${delPreview.readers.join(", ")})` : " (none hold this person)"} so their face stops working at the door.</span>
                  </label>
                  <p className="sub" style={{ marginTop: 10 }}>The Face ID is then blocked: a reader that still sends it cannot re-create the person. Adding or importing them again lifts the block.</p>
                </>
              )}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
                <button type="button" className="btn btn-outline-reports" onClick={() => setDelTarget(null)} disabled={deleting}>Cancel</button>
                <button type="button" className="employee-mgmt-btn-delete" onClick={confirmDelete} disabled={deleting || !delPreview || !!delPreview.error}>{deleting ? "Deleting…" : "Delete"}</button>
              </div>
            </div>
          </div>
        </div>
      )}
      {dupOpen && (
        <div className="modal-overlay" onClick={() => !dupBusy && setDupOpen(false)} style={{ zIndex: 60 }}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" style={{ maxWidth: 640 }}>
            <div className="emp-edit-head">
              <div><h3>Clean up student records</h3><span className="emp-edit-sub">Students a shared reader created as staff. They stay on the readers; only the staff record goes.</span></div>
              <button type="button" className="modal-close" onClick={() => setDupOpen(false)} aria-label="Close">×</button>
            </div>
            <div style={{ padding: "4px 18px 18px" }}>
              {!dups ? <p className="sub">Checking…</p> : dups.length === 0 ? <p className="sub">No student is listed as staff.</p> : (
                <div className="table-scroll" style={{ maxHeight: 320 }}>
                  <table className="table table-compact">
                    <thead><tr><th>ID</th><th>Listed as staff</th><th>Student</th><th>Department (staff)</th></tr></thead>
                    <tbody>{dups.map((d: any) => (
                      <tr key={d.EmployeeCode}><td><strong>{d.EmployeeCode}</strong></td><td>{d.EmployeeName}</td><td>{d.StudentName}</td><td>{d.Department || "—"}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
                <button type="button" className="btn btn-outline-reports" onClick={() => setDupOpen(false)} disabled={dupBusy}>Close</button>
                {!!dups?.length && <button type="button" className="employee-mgmt-btn-delete" onClick={confirmDups} disabled={dupBusy}>{dupBusy ? "Removing…" : `Remove ${dups.length} from staff`}</button>}
              </div>
            </div>
          </div>
        </div>
      )}
      {xlOpen && (
        <div className="modal-overlay" onClick={closeImport}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" style={{ maxWidth: 920 }}>
            <div className="emp-edit-card">
              <div className="emp-edit-head">
                <div className="emp-edit-title">
                  <span className="emp-avatar" aria-hidden>⇪</span>
                  <div>
                    <h3>Import employees from Excel</h3>
                    <span className="emp-edit-sub">Upload a spreadsheet, check the column mapping, then confirm.</span>
                  </div>
                </div>
                <button type="button" className="modal-close" onClick={closeImport} aria-label="Close">×</button>
              </div>

              <div className="emp-edit-scroll">
                {xlError && <div className="emp-error" role="alert">{xlError}</div>}

                {/* Stage 1: pick a file */}
                <section className="emp-section">
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
                    <input
                      type="file"
                      accept=".xlsx,.xls"
                      onChange={(e) => onImportFileChosen(e.target.files?.[0] ?? null)}
                      disabled={xlBusy}
                    />
                    <button type="button" className="btn-outline-reports" onClick={() => api.downloadImportTemplate().catch((err) => setXlError(err instanceof Error ? err.message : "Could not download template."))}>
                      Download template
                    </button>
                    {xlBusy && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Reading…</span>}
                  </div>
                  <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--text-muted)" }}>
                    Accepts .xlsx. New Departments, Designations, Employee Types and Organizations are created automatically. Existing employees (matched by Employee Code) are updated.
                  </p>
                </section>

                {/* Stage 2: map columns */}
                {xlFile && xlColumns.length > 0 && (
                  <section className="emp-section">
                    <SectionHead icon={Icons.document} title="Column mapping" desc="Point each spreadsheet column at the right field. Unneeded columns can stay ignored." />
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                      <label style={{ fontSize: 13 }}>Header is on row</label>
                      <input type="number" min={1} value={xlHeaderRow} onChange={(e) => changeHeaderRow(Math.max(1, Number(e.target.value) || 1))} style={{ width: 70 }} disabled={xlBusy} />
                    </div>
                    <div style={{ overflowX: "auto" }}>
                      <table className="table">
                        <thead>
                          <tr><th>Column</th><th>Sample values</th><th>Import as</th></tr>
                        </thead>
                        <tbody>
                          {xlColumns.map((col: any) => (
                            <tr key={col.index}>
                              <td style={{ whiteSpace: "nowrap" }}><strong>{col.letter}</strong>{col.header ? ` · ${col.header}` : ""}</td>
                              <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{(col.samples || []).join(", ") || "—"}</td>
                              <td>
                                <select value={xlColToField[col.index] || ""} onChange={(e) => setColMapping(col.index, e.target.value)} disabled={xlBusy}>
                                  <option value="">— Ignore —</option>
                                  {xlFields.map((f) => (
                                    <option key={f} value={f}>{IMPORT_FIELD_LABELS[f] || f}</option>
                                  ))}
                                </select>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}

                {/* Stage 3: preview */}
                {xlPreview && (
                  <section className="emp-section">
                    <SectionHead icon={Icons.employees} title="Preview" desc="Nothing is saved until you click Import." />
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 10, fontSize: 14 }}>
                      <span><strong>{xlPreview.summary?.total ?? 0}</strong> rows</span>
                      <span style={{ color: "#16a34a" }}><strong>{xlPreview.summary?.to_create ?? 0}</strong> to add</span>
                      <span style={{ color: "#2563eb" }}><strong>{xlPreview.summary?.to_update ?? 0}</strong> to update</span>
                      <span style={{ color: "#dc2626" }}><strong>{xlPreview.summary?.errors ?? 0}</strong> errors</span>
                    </div>
                    {(xlPreview.summary?.total ?? 0) === 0 && (
                      <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No importable rows. Make sure Employee Code and Employee Name are mapped and the header row is correct.</p>
                    )}
                    <div style={{ maxHeight: 260, overflow: "auto" }}>
                      <table className="table">
                        <thead style={{ position: "sticky", top: 0, background: "#f8fafc" }}>
                          <tr><th>Row</th><th>Code</th><th>Name</th><th>Department</th><th>Designation</th><th>Action</th><th>Notes</th></tr>
                        </thead>
                        <tbody>
                          {(xlPreview.rows || []).slice(0, 200).map((r: any) => (
                            <tr key={r.row_number}>
                              <td>{r.row_number}</td>
                              <td>{r.EmployeeCode ?? "—"}</td>
                              <td>{r.EmployeeName ?? "—"}</td>
                              <td>{r.Department ?? "—"}</td>
                              <td>{r.Designation ?? "—"}</td>
                              <td>
                                <span className={"badge " + (r.action === "error" ? "badge-red" : r.action === "update" ? "badge-green" : "badge-green")}>{r.action}</span>
                              </td>
                              <td style={{ fontSize: 12, color: r.action === "error" ? "#dc2626" : "var(--text-muted)" }}>{(r.messages || []).join(" ") || ""}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {(xlPreview.rows || []).length > 200 && (
                      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Showing first 200 of {xlPreview.rows.length} rows.</p>
                    )}
                  </section>
                )}

                <div className="emp-edit-actions">
                  <button type="button" className="btn btn-outline-reports" onClick={closeImport}>Cancel</button>
                  <button type="button" className="btn btn-primary-purple" onClick={doImportCommit}
                    disabled={xlBusy || !xlPreview || (xlPreview.summary?.total ?? 0) === 0}>
                    {xlBusy ? "Working…" : `Import ${(xlPreview?.summary?.to_create ?? 0) + (xlPreview?.summary?.to_update ?? 0)} employees`}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {codeOpen && (
        <div className="modal-overlay" onClick={() => !changingCode && setCodeOpen(false)} style={{ zIndex: 60 }}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" style={{ maxWidth: 460 }}>
            <div className="emp-edit-card">
              <div className="emp-edit-head">
                <div className="emp-edit-title">
                  <span className="emp-avatar" aria-hidden>#</span>
                  <div>
                    <h3>Change Face ID</h3>
                    <span className="emp-edit-sub">Current Face ID: {editingEmployeeCode}</span>
                  </div>
                </div>
                <button type="button" className="modal-close" onClick={() => setCodeOpen(false)} aria-label="Close">×</button>
              </div>
              <div className="emp-edit-scroll">
                {codeError && <div className="emp-error" role="alert">{codeError}</div>}
                <section className="emp-section">
                  <div className="field">
                    <label htmlFor="new-emp-code">New Face ID <Req /></label>
                    <input id="new-emp-code" value={newCode} autoFocus placeholder="e.g. CSC26018"
                      onChange={(e) => { setNewCode(e.target.value); setCodeError(""); }} />
                    <span className="field-hint">
                      Re-points this person's punches, attendance, face enrollment, biometrics, leaves and portal login to the new code, all at once.
                      It must be unique and must match the ID on the device/camera.
                    </span>
                  </div>
                </section>
                <div className="emp-edit-actions">
                  <button type="button" className="btn btn-outline-reports" onClick={() => setCodeOpen(false)} disabled={changingCode}>Cancel</button>
                  <button type="button" className="btn btn-primary-purple" onClick={doChangeCode} disabled={changingCode || !newCode.trim()}>
                    {changingCode ? "Changing…" : "Change Face ID"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {moveOpen && (
        <div className="modal-overlay" onClick={() => !moving && setMoveOpen(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" style={{ maxWidth: 520 }}>
            <div className="emp-edit-card">
              <div className="emp-edit-head">
                <div className="emp-edit-title">
                  <span className="emp-avatar" aria-hidden>⇄</span>
                  <div>
                    <h3>Move {selectedIds.size} employee{selectedIds.size === 1 ? "" : "s"}</h3>
                    <span className="emp-edit-sub">Reassign to a target organization, school and/or department.</span>
                  </div>
                </div>
                <button type="button" className="modal-close" onClick={() => setMoveOpen(false)} aria-label="Close">×</button>
              </div>
              <div className="emp-edit-scroll">
                <section className="emp-section">
                  <div className="emp-grid">
                    <div className="field">
                      <label>Organization</label>
                      <select value={moveOrg} onChange={(e) => { setMoveOrg(e.target.value); setMoveDept(""); }}>
                        <option value="">— Keep current —</option>
                        {organizations.map((o) => <option key={o.OrganizationId} value={String(o.OrganizationId)}>{o.OrgName}</option>)}
                      </select>
                    </div>
                    <div className="field">
                      <label>School</label>
                      <select value={moveSchool} onChange={(e) => setMoveSchool(e.target.value)}>
                        <option value="">— Keep current —</option>
                        {schools.map((x) => <option key={x.SchoolId} value={String(x.SchoolId)}>{x.SchoolName}</option>)}
                      </select>
                    </div>
                    <div className="field">
                      <label>Department</label>
                      <select value={moveDept} onChange={(e) => setMoveDept(e.target.value)}>
                        <option value="">— Keep current —</option>
                        {departmentsList
                          .filter((d) => !moveOrg || d.OrganizationId === Number(moveOrg))
                          .map((d) => <option key={d.DepartmentId} value={d.DepartmentName}>{d.DepartmentName}</option>)}
                      </select>
                    </div>
                  </div>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "8px 0 0" }}>
                    Pick at least one. A field left on "Keep current" is unchanged for every selected employee. Changing the organization filters the department list to that organization.
                  </p>
                </section>
                <div className="emp-edit-actions">
                  <button type="button" className="btn btn-outline-reports" onClick={() => setMoveOpen(false)} disabled={moving}>Cancel</button>
                  <button type="button" className="btn btn-primary-purple" onClick={doMove} disabled={moving || (!moveOrg && !moveDept && !moveSchool)}>
                    {moving ? "Moving…" : "Move employees"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {assignOpen && (
        <div className="modal-overlay" onClick={() => !assigning && setAssignOpen(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" style={{ maxWidth: 520 }}>
            <div className="emp-edit-card">
              <div className="emp-edit-head">
                <div className="emp-edit-title">
                  <span className="emp-avatar" aria-hidden>⏱</span>
                  <div>
                    <h3>Assign shift to {selectedIds.size} employee{selectedIds.size === 1 ? "" : "s"}</h3>
                    <span className="emp-edit-sub">Their earlier shift ends the day before the start date.</span>
                  </div>
                </div>
                <button type="button" className="modal-close" onClick={() => setAssignOpen(false)} aria-label="Close">×</button>
              </div>
              <div className="emp-edit-scroll">
                <section className="emp-section">
                  <div className="emp-grid">
                    <div className="field field-full">
                      <label>Shift <Req /></label>
                      <select value={assignShiftId} onChange={(e) => setAssignShiftId(e.target.value)}>
                        <option value="">Select a shift…</option>
                        {shifts.map((x) => <option key={x.ShiftId} value={x.ShiftId}>{x.ShiftName}{x.StartTime ? ` (${String(x.StartTime).slice(0, 5)}–${String(x.EndTime).slice(0, 5)})` : ""}</option>)}
                      </select>
                    </div>
                    <div className="field">
                      <label>From <Req /></label>
                      <input type="date" value={assignFrom} onChange={(e) => setAssignFrom(e.target.value)} />
                    </div>
                    <div className="field">
                      <label>Until (optional)</label>
                      <input type="date" value={assignTo} min={assignFrom} onChange={(e) => setAssignTo(e.target.value)} />
                    </div>
                  </div>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "8px 0 0" }}>
                    Leave "Until" empty for no end date. Attendance from the start date is recalculated for these employees.
                  </p>
                </section>
                <div className="emp-edit-actions">
                  <button type="button" className="btn btn-outline-reports" onClick={() => setAssignOpen(false)} disabled={assigning}>Cancel</button>
                  <button type="button" className="btn btn-primary-purple" onClick={doAssign} disabled={assigning || !assignShiftId || !assignFrom}>
                    {assigning ? "Assigning…" : "Assign shift"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <section className="employee-mgmt-list-card">
        <div className="employee-mgmt-list-toolbar">
          <div className="employee-mgmt-list-search-wrap">
            <span className="search-icon"><SearchIcon /></span>
            <input type="search" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search by name, code, Face ID, department..." aria-label="Search employees" />
          </div>
          <select className="input" value={orgFilter} onChange={(e) => { setOrgFilter(e.target.value); setPage(1); }} aria-label="Filter by institution" style={{ maxWidth: 240 }}>
            <option value="">{campus ? campus.name : "All institutions"}</option>
            {!campus && organizations.map((o) => <option key={o.OrganizationId} value={String(o.OrganizationId)}>{o.OrgName}</option>)}
          </select>
          <select className="input" value={schoolFilter} onChange={(e) => { setSchoolFilter(e.target.value); setPage(1); }} aria-label="Filter by school" style={{ maxWidth: 240 }}>
            <option value="">All schools</option>
            {schools.map((x) => <option key={x.SchoolId} value={String(x.SchoolId)}>{x.SchoolName}</option>)}
          </select>
          <select className="input" value={deptFilter} onChange={(e) => { setDeptFilter(e.target.value); setPage(1); }} aria-label="Filter by department" style={{ maxWidth: 240 }}>
            <option value="">All departments</option>
            {deptOptions.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            {selectedIds.size > 0 && (
              <>
                <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{selectedIds.size} selected</span>
                <button type="button" className="btn btn-primary-purple" onClick={openAssign}>Assign shift…</button>
                <button type="button" className="btn btn-primary-purple" onClick={openMove}>Move…</button>
                <button type="button" className="btn-outline-gray" onClick={clearSelection}>Clear</button>
              </>
            )}
            <span className="employee-mgmt-list-count">{filteredRows.length} employee{filteredRows.length !== 1 ? "s" : ""}</span>
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead style={{ position: "sticky", top: 0, background: "#f8fafc", zIndex: 1, boxShadow: "0 1px 0 #e2e8f0" }}>
              <tr>
                <th style={{ width: 34 }}>
                  <input type="checkbox" checked={allOnPageSelected} onChange={toggleSelectPage}
                    aria-label="Select all on this page" title="Select all on this page" />
                </th>
                <th>Employee Code</th>
                <th>Sort No</th>
                <th>Face ID</th>
                <th>Name</th>
                <th>Department</th>
                <th>School</th>
                <th>Shift</th>
                <th>Role</th>
                <th>Category</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {paginatedRows.map((row: any) => (
                <tr key={row.EmployeeId} style={selectedIds.has(row.EmployeeId) ? { background: "rgba(124,58,237,0.06)" } : undefined}>
                  <td>
                    <input type="checkbox" checked={selectedIds.has(row.EmployeeId)} onChange={() => toggleSelect(row.EmployeeId)}
                      aria-label={`Select ${row.EmployeeName}`} />
                  </td>
                  <td>{row.StringCode || row.EmployeeCode}</td>
                  <td>{row.ShortNo || "—"}</td>
                  <td>{row.EmployeeCode}</td>
                  <td>{row.EmployeeName}</td>
                  <td>{row.Department ?? "—"}</td>
                  <td>{row.SchoolId ? (schools.find((x) => x.SchoolId === row.SchoolId)?.SchoolName ?? `#${row.SchoolId}`) : "—"}</td>
                  <td>{row.CurrentShift || "—"}</td>
                  <td>{row.Role ?? "—"}</td>
                  <td>{row.CategoryId ? (categories.find((c) => c.CategoryId === row.CategoryId)?.CategoryName ?? `#${row.CategoryId}`) : "—"}</td>
                  <td>
                    <div className="employee-mgmt-action-cell">
                      <button type="button" className="employee-mgmt-btn-edit" onClick={() => startEdit(row)}>Edit</button>
                      <button type="button" className="employee-mgmt-btn-delete" onClick={() => askDelete(row)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
              {paginatedRows.length === 0 && (
                <tr>
                  <td colSpan={10} style={{ textAlign: "center", padding: "24px", color: "#64748b" }}>No employees found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {filteredRows.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Rows per page</span>
              <select className="input" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} aria-label="Rows per page">
                {[10, 20, 30, 40, 50, 75, 100].map((n) => <option key={n} value={n}>{n}</option>)}
                <option value={-1}>All</option>
              </select>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button type="button" className="btn-outline-gray" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={currentPage <= 1}>Previous</button>
              <span style={{ fontSize: 13 }}>Page {currentPage} of {totalPages}</span>
              <button type="button" className="btn-outline-gray" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage >= totalPages}>Next</button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
