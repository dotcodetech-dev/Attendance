import { clearToken, getToken } from "../store/auth";

/** Fired once when any request comes back 401 (expired/invalid session), so the
 *  app can send the user back to Login instead of pages quietly showing no data. */
export const SESSION_EXPIRED_EVENT = "auth:session-expired";
let sessionExpiredNotified = false;

/**
 * Fired when a request fails to reach the server at all (dropped connection, proxy
 * timeout, DNS hiccup) rather than coming back with an HTTP error — the case that used
 * to look exactly like "the app is just broken", with no indication a retry might help.
 * Cleared again the moment any request succeeds.
 */
export const CONNECTION_ISSUE_EVENT = "api:connection-issue";
export const CONNECTION_OK_EVENT = "api:connection-ok";
let connectionIssueNotified = false;
// Only a backstop for a truly hung connection. Several calls are legitimately slow (reading users
// from a reader over the SDK, transfers, recalculating a month for hundreds of staff, imports), so
// this must stay well above the slowest real operation.
const DEFAULT_TIMEOUT_MS = 180000;

/**
 * API base resolution:
 *  - explicit VITE_API_BASE_URL wins (build-time override);
 *  - when the app is served from anything other than the Vite dev server
 *    (port 5173) — e.g. through the IIS proxy on port 80 — use the SAME origin
 *    so it works on whatever host/port it's opened from;
 *  - otherwise fall back to the local dev backend.
 */
function resolveBaseUrl(): string {
  const envBase = import.meta.env.VITE_API_BASE_URL;
  if (envBase) return envBase;
  if (typeof window !== "undefined" && window.location.port !== "5173") {
    return `${window.location.origin}/api/v1`;
  }
  return "http://localhost:8000/api/v1";
}

const BASE_URL = resolveBaseUrl();

/** Backend root (no /api/v1) for health check */
export function getBackendBaseUrl(): string {
  return BASE_URL.replace(/\/api\/v1\/?$/, "") || "http://localhost:8000";
}

type RequestOptions = RequestInit & { signal?: AbortSignal; timeoutMs?: number };

async function request(path: string, init?: RequestOptions) {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  // A hung reverse-proxy connection otherwise leaves a page "loading" forever with no
  // error at all. Give every call a ceiling, unless the caller already supplies its own signal.
  const ownController = init?.signal ? null : new AbortController();
  const timeoutId = ownController ? window.setTimeout(() => ownController.abort(), init?.timeoutMs ?? DEFAULT_TIMEOUT_MS) : null;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...init, headers, signal: init?.signal ?? ownController?.signal });
  } catch (e) {
    // fetch() itself rejects (not an HTTP error response) when the connection never completes:
    // offline, DNS failure, dropped TCP connection, or our own timeout aborting it.
    const timedOut = e instanceof Error && e.name === "AbortError" && !init?.signal;
    // A slow reply is not a lost connection: only a request that never reached the server raises the banner.
    if (!timedOut && !connectionIssueNotified) {
      connectionIssueNotified = true;
      window.dispatchEvent(new Event(CONNECTION_ISSUE_EVENT));
    }
    throw new Error(timedOut ? "The server took too long to respond. Check the connection and try again." : "Could not reach the server. Check the connection and try again.");
  } finally {
    if (timeoutId !== null) window.clearTimeout(timeoutId);
  }
  if (connectionIssueNotified) {
    connectionIssueNotified = false;
    window.dispatchEvent(new Event(CONNECTION_OK_EVENT));
  }
  if (res.status === 401 && token) {
    // The session token is missing/expired/invalid server-side. Every call will keep failing
    // the same way (pages silently showing "no data" forever) until the user signs in again —
    // so clear it and send the app back to Login once, instead of leaving stale screens up.
    clearToken();
    if (!sessionExpiredNotified) {
      sessionExpiredNotified = true;
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
  }
  if (!res.ok) {
    const text = await res.text();
    let detailMessage = "";
    if (text) {
      try {
        const parsed = JSON.parse(text);
        if (typeof parsed?.detail === "string") {
          detailMessage = parsed.detail;
        } else if (Array.isArray(parsed?.detail) && parsed.detail.length > 0) {
          const first = parsed.detail[0];
          if (typeof first?.msg === "string") {
            detailMessage = first.msg;
          }
        }
      } catch {
        // Non-JSON response (e.g. IIS HTML error page) — don't use raw HTML as the message.
      }
    }
    if (!detailMessage) {
      const isHtml = text.trimStart().startsWith("<") || (res.headers.get("content-type") || "").includes("text/html");
      detailMessage = isHtml
        ? `Backend unreachable (HTTP ${res.status}). Is the API server running?`
        : text || `HTTP ${res.status}`;
    }
    throw new Error(detailMessage);
  }
  if (res.status === 204) return null;
  return res.json();
}

/** Pull a human-readable message out of a failed fetch Response. */
async function extractError(res: Response): Promise<string> {
  try {
    const parsed = await res.json();
    if (typeof parsed?.detail === "string") return parsed.detail;
    if (Array.isArray(parsed?.detail) && typeof parsed.detail[0]?.msg === "string") return parsed.detail[0].msg;
  } catch {
    /* non-JSON body */
  }
  return `HTTP ${res.status}`;
}

const LOGIN_TIMEOUT_MS = 15000;

/** Serialize a report filter object to a query string, dropping empty values. */
function qstr(q: Record<string, string | number | boolean | undefined>): string {
  const s = new URLSearchParams();
  Object.entries(q).forEach(([k, v]) => { if (v !== undefined && v !== "") s.set(k, String(v)); });
  const str = s.toString();
  return str ? `?${str}` : "";
}

export const api = {
  /** Ping backend /health to see if server is reachable (no auth). */
  checkBackendHealth: async (): Promise<boolean> => {
    const base = getBackendBaseUrl();
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 5000);
    try {
      const res = await fetch(`${base}/health`, { signal: controller.signal });
      return res.ok;
    } catch {
      return false;
    } finally {
      window.clearTimeout(timeoutId);
    }
  },

  login: async (username: string, password: string) => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), LOGIN_TIMEOUT_MS);
    try {
      const res = await request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
        signal: controller.signal,
      });
      sessionExpiredNotified = false; // a fresh login means a future expiry should trigger the redirect again
      return res;
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") {
        throw new Error("Request timed out. Is the backend running at " + getBackendBaseUrl() + "?");
      }
      throw e;
    } finally {
      window.clearTimeout(timeoutId);
    }
  },

  getDashboard: () => request("/dashboard/summary"),
  getDevices: () => request("/devices"),
  createDevice: (payload: unknown) => request("/devices", { method: "POST", body: JSON.stringify(payload) }),
  updateDevice: (id: number, payload: unknown) =>
    request(`/devices/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  getDeviceUsers: (deviceId: number) => request(`/devices/${deviceId}/users`),
  getDeviceMachineUsers: (deviceId: number) => request(`/devices/${deviceId}/machine-users`),
  // Push-channel readers: ask the reader to re-send its users/templates (arrive via OPERLOG).
  refreshDeviceMachineUsers: (deviceId: number) => request(`/devices/${deviceId}/machine-users/refresh`, { method: "POST" }),
  /** Push readers: send the server's employee names to the reader (admin rights on the reader are kept). */
  sendNamesToDevice: (deviceId: number) => request(`/devices/${deviceId}/machine-users/send-names`, { method: "POST" }),
  /** When the reader last polled and what the server holds for it (explains an empty user list). */
  getReaderStatus: (deviceId: number) => request(`/devices/${deviceId}/reader-status`),
  importEmployeesFromDevice: (deviceId: number, payload?: unknown, options?: { signal?: AbortSignal }) =>
    request(`/devices/${deviceId}/import-employees`, { method: "POST", body: JSON.stringify(payload || {}), signal: options?.signal }),
  syncEmployeesToDevice: (deviceId: number, payload?: unknown) =>
    request(`/devices/${deviceId}/sync-employees`, { method: "POST", body: JSON.stringify(payload || {}) }),
  pullDeviceUserPhoto: (deviceId: number, employeeCode: string) =>
    request(`/devices/${deviceId}/machine-users/${encodeURIComponent(employeeCode)}/photo/pull`, { method: "POST" }),
  deleteDeviceMachineUser: (deviceId: number, employeeCode: string) =>
    request(`/devices/${deviceId}/machine-users/${encodeURIComponent(employeeCode)}`, { method: "DELETE" }),
  connectDevice: (deviceId: number) => request(`/devices/${deviceId}/connect`, { method: "POST" }),
  enrollOnDevice: (deviceId: number, payload: unknown) =>
    request(`/devices/${deviceId}/enroll`, { method: "POST", body: JSON.stringify(payload) }),
  getEnrollStatus: (
    deviceId: number,
    employeeRef: string,
    bioType: string,
    updateMode = false,
    allowFallbackUserPresence = false
  ) =>
    request(
      `/devices/${deviceId}/enroll-status?employee_ref=${encodeURIComponent(employeeRef)}&bio_type=${encodeURIComponent(
        bioType
      )}&update_mode=${updateMode ? "true" : "false"}&allow_fallback_user_presence=${
        allowFallbackUserPresence ? "true" : "false"
      }`
    ),
  testDeviceConnection: (ip: string, port = 4370, commKey?: number | null) =>
    request("/devices/test-connection", {
      method: "POST",
      body: JSON.stringify({ DeviceIPAddress: ip, Port: port, CommKey: commKey ?? null }),
    }),
  deleteDevice: (id: number) => request(`/devices/${id}`, { method: "DELETE" }),
  fetchDeviceAttendance: (deviceId: number, port = 4370) =>
    request(`/devices/${deviceId}/fetch-attendance?port=${port}`, { method: "POST" }),
  getDeviceCommLog: (serial?: string, limit = 60) => {
    const s = new URLSearchParams({ limit: String(limit) });
    if (serial) s.set("serial", serial);
    return request(`/devices/comm-log?${s.toString()}`);
  },

  getEmployees: () => request("/employees"),
  createEmployee: (payload: unknown) => request("/employees", { method: "POST", body: JSON.stringify(payload) }),
  updateEmployee: (id: number, payload: unknown) => request(`/employees/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteEmployee: (id: number, removeFromReaders = true) => request(`/employees/${id}?remove_from_readers=${removeFromReaders}`, { method: "DELETE" }),
  getEmployeeDeletePreview: (id: number) => request(`/employees/${id}/delete-preview`),
  getBlockedPins: () => request("/employees/blocked-pins"),
  allowPinAgain: (pin: string) => request(`/employees/blocked-pins/${encodeURIComponent(pin)}`, { method: "DELETE" }),
  getStudentDuplicates: () => request("/employees/student-duplicates"),
  deleteStudentDuplicates: (codes: string[]) => request("/employees/student-duplicates/delete", { method: "POST", body: JSON.stringify({ codes }) }),
  // Re-point an employee's Code everywhere (bio, photos, punches, attendance, login...).
  changeEmployeeCode: (id: number, newCode: string) =>
    request(`/employees/${id}/change-code`, { method: "POST", body: JSON.stringify({ new_code: newCode }) }),
  // Bulk-move employees to a target Organization and/or Department.
  moveEmployees: (payload: { employee_ids: number[]; OrganizationId?: number; Department?: string }) =>
    request("/employees/move", { method: "POST", body: JSON.stringify(payload) }),

  // ---- Excel bulk import ----
  // Detect the header row + list columns so the user can map them.
  importInspect: async (file: File) => {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE_URL}/employees/import/inspect`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json();
  },
  // Dry run (commit=false) — validate and show what would happen.
  importPreview: async (file: File, mapping: unknown) => {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    form.append("mapping", JSON.stringify(mapping));
    const res = await fetch(`${BASE_URL}/employees/import/preview`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json();
  },
  // Write to the database (commit=true).
  importCommit: async (file: File, mapping: unknown) => {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    form.append("mapping", JSON.stringify(mapping));
    const res = await fetch(`${BASE_URL}/employees/import/commit`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json();
  },
  // Download the ready-to-fill .xlsx template (auth'd blob → save).
  downloadImportTemplate: async () => {
    const token = getToken();
    const res = await fetch(`${BASE_URL}/employees/import/template`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(await extractError(res));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "employee_import_template.xlsx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  addBiometric: (employeeRef: string, payload: unknown) =>
    request(`/employees/${encodeURIComponent(employeeRef)}/biometrics`, { method: "POST", body: JSON.stringify(payload) }),
  getEmployeePhoto: (employeeRef: string, includeData = true) =>
    request(`/employees/${encodeURIComponent(employeeRef)}/photo?include_data=${includeData ? "true" : "false"}`),
  upsertEmployeePhoto: (employeeRef: string, payload: unknown) =>
    request(`/employees/${encodeURIComponent(employeeRef)}/photo`, { method: "PUT", body: JSON.stringify(payload) }),

  transferBiometric: (payload: unknown) => request("/biometrics/transfer", { method: "POST", body: JSON.stringify(payload) }),
  getAutoSync: () => request("/biometrics/auto-sync"),
  setAutoSync: (enabled: boolean) => request("/biometrics/auto-sync", { method: "PUT", body: JSON.stringify({ enabled }) }),
  getTransferJob: (jobId: number) => request(`/biometrics/transfer-jobs/${jobId}`),
  listTransferJobs: () => request("/biometrics/transfer-jobs"),
  retryTransferJob: (jobId: number) => request(`/biometrics/transfer-jobs/${jobId}/retry`, { method: "POST" }),
  // The server allows up to 10 minutes for a direct SDK push; give the browser a little longer than that.
  executeTransferJobSdk: (jobId: number) =>
    request(`/biometrics/transfer-jobs/${jobId}/execute-sdk`, { method: "POST", timeoutMs: 11 * 60 * 1000 }),
  getCommands: () => request("/commands"),
  getAdmsLog: (deviceId: number, limit = 200) => request(`/devices/${deviceId}/adms-log?limit=${limit}`),
  runReaderDiagnostics: (deviceId: number, pin?: string) =>
    request(`/devices/${deviceId}/diagnostics`, { method: "POST", body: JSON.stringify({ pin: pin || null }) }),
  createCommand: (payload: unknown) => request("/commands", { method: "POST", body: JSON.stringify(payload) }),
  getLogs: (limit = 500) => request(`/attendance/logs?limit=${limit}`),

  getAttendanceLogs: (params: {
    limit?: number;
    device_id?: number;
    employee_code?: string;
    from_date?: string;
    to_date?: string;
  }) => {
    const search = new URLSearchParams();
    if (params.limit) search.set("limit", String(params.limit));
    if (params.device_id != null) search.set("device_id", String(params.device_id));
    if (params.employee_code) search.set("employee_code", params.employee_code);
    if (params.from_date) search.set("from_date", params.from_date);
    if (params.to_date) search.set("to_date", params.to_date);
    const qs = search.toString();
    return request(`/attendance/logs${qs ? `?${qs}` : ""}`);
  },
  getEmployeeAttendanceSummary: (params: {
    employee_code: string;
    year: number;
    month: number;
  }) => {
    const search = new URLSearchParams();
    search.set("employee_code", params.employee_code);
    search.set("year", String(params.year));
    search.set("month", String(params.month));
    return request(`/attendance/employee-summary?${search.toString()}`);
  },

  getAttendanceRules: () => request("/attendance/rules"),
  updateAttendanceRules: (payload: { enabled: boolean; days: number; mode: string; duplicate_seconds?: number; direction_mode?: string }) =>
    request("/attendance/rules", { method: "PUT", body: JSON.stringify(payload) }),
  // Apply the punch rule to stored punches (delete repeats, renumber IN/OUT) + recalc.
  repairPunches: (p: { from_date: string; to_date?: string }) => {
    const s = new URLSearchParams({ from_date: p.from_date });
    if (p.to_date) s.set("to_date", p.to_date);
    return request(`/attendance/punches/repair?${s.toString()}`, { method: "POST" });
  },
  getLateReview: (p: { employee_code: string; year: number; month: number }) =>
    request(`/attendance/late-review?employee_code=${encodeURIComponent(p.employee_code)}&year=${p.year}&month=${p.month}`),
  previewLeaveDays: (p: { employee_code: string; leave_config_id: number; from_date: string; to_date: string }) =>
    request(`/leaves/days?employee_code=${encodeURIComponent(p.employee_code)}&leave_config_id=${p.leave_config_id}&from_date=${p.from_date}&to_date=${p.to_date}`),
  recalculateAttendance: (payload: { from_date: string; to_date: string; employee_code?: string }) =>
    request("/attendance/recalculate", { method: "POST", body: JSON.stringify(payload) }),
  downloadAttendanceCsv: async (params: { from_date: string; to_date: string; employee_code?: string }) => {
    const search = new URLSearchParams();
    search.set("from_date", params.from_date);
    search.set("to_date", params.to_date);
    if (params.employee_code) search.set("employee_code", params.employee_code);
    const token = getToken();
    const res = await fetch(`${BASE_URL}/attendance/processed/export.csv?${search.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Export failed (${res.status})`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `attendance_${params.from_date}_${params.to_date}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  getProcessedAttendance: (params: {
    from_date: string;
    to_date: string;
    employee_code?: string;
    status?: string;
    limit?: number;
  }) => {
    const search = new URLSearchParams();
    search.set("from_date", params.from_date);
    search.set("to_date", params.to_date);
    if (params.employee_code) search.set("employee_code", params.employee_code);
    if (params.status) search.set("status", params.status);
    if (params.limit) search.set("limit", String(params.limit));
    return request(`/attendance/processed?${search.toString()}`);
  },

  // ---- Masters: organizations / departments / employee types ----
  getOrganizations: (includeInactive = false) =>
    request(`/masters/organizations${includeInactive ? "?include_inactive=true" : ""}`),
  createOrganization: (payload: { OrgName: string; Address?: string }) =>
    request("/masters/organizations", { method: "POST", body: JSON.stringify(payload) }),
  updateOrganizationMaster: (id: number, payload: { OrgName: string; Address?: string; IsActive?: string }) =>
    request(`/masters/organizations/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  getDepartments: (organizationId?: number, includeInactive = false) => {
    const s = new URLSearchParams();
    if (organizationId) s.set("organization_id", String(organizationId));
    if (includeInactive) s.set("include_inactive", "true");
    const qs = s.toString();
    return request(`/masters/departments${qs ? `?${qs}` : ""}`);
  },
  createDepartment: (payload: { OrganizationId: number; DepartmentName: string; SchoolId?: number | null }) =>
    request("/masters/departments", { method: "POST", body: JSON.stringify(payload) }),
  updateDepartment: (id: number, payload: { OrganizationId: number; DepartmentName: string; IsActive?: string; SchoolId?: number | null }) =>
    request(`/masters/departments/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  getDesignations: (includeInactive = false) =>
    request(`/masters/designations${includeInactive ? "?include_inactive=true" : ""}`),
  createDesignation: (payload: { DesignationName: string }) =>
    request("/masters/designations", { method: "POST", body: JSON.stringify(payload) }),
  updateDesignation: (id: number, payload: { DesignationName: string; IsActive?: string }) =>
    request(`/masters/designations/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  getEmployeeTypes: (includeInactive = false) =>
    request(`/masters/employee-types${includeInactive ? "?include_inactive=true" : ""}`),
  createEmployeeType: (payload: { TypeName: string }) =>
    request("/masters/employee-types", { method: "POST", body: JSON.stringify(payload) }),
  updateEmployeeType: (id: number, payload: { TypeName: string; IsActive?: string }) =>
    request(`/masters/employee-types/${id}`, { method: "PUT", body: JSON.stringify(payload) }),

  getSchools: (includeInactive = false) =>
    request(`/masters/schools${includeInactive ? "?include_inactive=true" : ""}`),
  createSchool: (payload: { SchoolName: string; OrganizationId?: number | null }) =>
    request("/masters/schools", { method: "POST", body: JSON.stringify(payload) }),
  updateSchool: (id: number, payload: { SchoolName: string; IsActive?: string; OrganizationId?: number | null }) =>
    request(`/masters/schools/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  // Organization > School > Department from an Excel sheet; commit=false is a dry run (what would change).
  importHierarchy: async (file: File, commit: boolean, orgMap: Record<string, number | null>) => {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    form.append("commit", commit ? "true" : "false");
    form.append("org_map", JSON.stringify(orgMap));
    const res = await fetch(`${BASE_URL}/masters/hierarchy-import`, {
      method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form,
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { const parsed = await res.json(); if (typeof parsed?.detail === "string") detail = parsed.detail; } catch { /* keep default */ }
      throw new Error(detail);
    }
    return res.json();
  },
  // Fill empty Organization > School > Department links from the employees' own data.
  linkMastersFromEmployees: () => request("/masters/link-from-employees", { method: "POST" }),

  // Configurable student dropdowns (Registered Year / Batch / Category).
  getStudentOptions: (includeInactive = false) =>
    request(`/masters/student-options${includeInactive ? "?include_inactive=true" : ""}`),
  createStudentOption: (payload: { OptionType: string; OptionValue: string }) =>
    request("/masters/student-options", { method: "POST", body: JSON.stringify(payload) }),
  updateStudentOption: (id: number, payload: { OptionValue?: string; IsActive?: string }) =>
    request(`/masters/student-options/${id}`, { method: "PUT", body: JSON.stringify(payload) }),

  // ---- HR Reports ----
  // Filters (organization_id, department, employee_type_id, category_id, ...) pass straight through as query params.
  getMonthlyRegister: (q: Record<string, string | number | boolean | undefined>) => request(`/reports/register${qstr(q)}`),
  getLeaveBalanceReport: (q: Record<string, string | number | boolean | undefined>) => request(`/reports/leave-balance${qstr(q)}`),
  // Present / Absent / Leave list for one day, grouped Department -> Employee.
  getDailyReport: (q: Record<string, string | number | boolean | undefined>) => request(`/reports/daily${qstr(q)}`),
  getLateOtReport: (q: Record<string, string | number | boolean | undefined>) => request(`/reports/late-ot${qstr(q)}`),
  getIndividualSheet: (p: { employee_code: string; year: number; month: number }) => {
    const s = new URLSearchParams({ employee_code: p.employee_code, year: String(p.year), month: String(p.month) });
    return request(`/reports/individual?${s.toString()}`);
  },
  // ---- Staff formatted reports (date-range: date-wise / weekly / yearly) ----
  getMusterTime: (q: Record<string, string | undefined>) => request(`/reports/muster-time${qstr(q)}`),
  getMusterLeave: (q: Record<string, string | undefined>) => request(`/reports/muster-leave${qstr(q)}`),
  getLateArrival: (q: Record<string, string | undefined>) => request(`/reports/late-arrival${qstr(q)}`),
  getEarlyDeparture: (q: Record<string, string | undefined>) => request(`/reports/early-departure${qstr(q)}`),
  getInOutList: (q: Record<string, string | undefined>) => request(`/reports/in-out${qstr(q)}`),
  getEmployeeList: (q: Record<string, string | undefined>) => request(`/reports/employee-list${qstr(q)}`),
  // Download any report as csv|xlsx|pdf, auth-aware blob download.
  downloadReport: async (report: string, fmt: "csv" | "xlsx" | "pdf", params: Record<string, string | number | boolean | undefined>) => {
    const s = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "") s.set(k, String(v)); });
    const token = getToken();
    const res = await fetch(`${BASE_URL}/reports/${report}/export.${fmt}?${s.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Export failed (${res.status})`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${report}.${fmt}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  // ---- Leave balances (per-employee entitlement) ----
  getEmployeeLeaveBalance: (employeeCode: string, year?: number) => {
    const s = new URLSearchParams();
    if (year) s.set("year", String(year));
    return request(`/leave-balance/employee/${encodeURIComponent(employeeCode)}?${s.toString()}`);
  },
  setEmployeeLeaveBalance: (payload: {
    EmployeeCode: string; LeaveConfigId: number; LeaveYear: number; AllowedLeaves: number; CarriedForward?: number;
  }) => request("/leave-balance/employee", { method: "PUT", body: JSON.stringify(payload) }),
  seedLeaveBalances: (year: number, overwrite = false) =>
    request(`/leave-balance/seed?year=${year}&overwrite=${overwrite ? "true" : "false"}`, { method: "POST" }),

  // ---- Mess Token ----
  getMessSettings: () => request("/mess/settings"),
  updateMessSettings: (payload: { enabled: boolean; meals?: any[]; mess_device_id?: number | null; auto_print?: boolean; student_module_enabled?: boolean; student_leaves_enabled?: boolean; student_absent_on_weekly_off?: boolean }) =>
    request("/mess/settings", { method: "PUT", body: JSON.stringify(payload) }),
  getMessKioskFeed: (sinceId: number) => request(`/mess/kiosk-feed?since_id=${sinceId}`),
  generateMessToken: (employee_code: string) =>
    request("/mess/token", { method: "POST", body: JSON.stringify({ employee_code }) }),
  reprintMessToken: (tokenId: number) =>
    request(`/mess/token/${tokenId}/reprint`, { method: "POST" }),
  getMessTokens: (params: { date?: string; meal?: string; employee_code?: string }) => {
    const s = new URLSearchParams();
    if (params.date) s.set("date", params.date);
    if (params.meal) s.set("meal", params.meal);
    if (params.employee_code) s.set("employee_code", params.employee_code);
    return request(`/mess/tokens?${s.toString()}`);
  },

  // ---- Student attendance module ----
  getFeatures: () => request("/settings/features"),
  // Leave approval: HOD / Manager, then Principal / Director
  getApprovalMe: () => request("/leave-approvals/me"),
  getLeaveApprovals: (tab: "waiting" | "open" | "decided" | "all") => request(`/leave-approvals?tab=${tab}`),
  getApprovers: () => request("/leave-approvals/approvers"),
  decideLeaveRequest: (id: number, action: "Approved" | "Rejected", remarks?: string) =>
    request(`/leave-approvals/${id}/decision`, { method: "POST", body: JSON.stringify({ action, remarks: remarks || null }) }),
  getUsers: () => request("/users"),
  linkUser: (payload: { login_name: string; employee_code?: string | null; role_name?: string }) =>
    request("/users/link", { method: "POST", body: JSON.stringify(payload) }),
  getNotifications: () => request("/notifications"),
  getStudents: (p: { department_id?: number; registered_year?: string; batch?: string; category?: string; section?: string; year?: number; q?: string; include_inactive?: boolean; status?: string } = {}) => {
    const s = new URLSearchParams();
    if (p.section) s.set("section", p.section);
    if (p.status) s.set("status", p.status);
    if (p.department_id) s.set("department_id", String(p.department_id));
    if (p.registered_year) s.set("registered_year", p.registered_year);
    if (p.batch) s.set("batch", p.batch);
    if (p.category) s.set("category", p.category);
    if (p.year) s.set("year", String(p.year));
    if (p.q) s.set("q", p.q);
    if (p.include_inactive) s.set("include_inactive", "true");
    return request(`/students?${s.toString()}`);
  },
  getStudentSummary: () => request("/students/summary"),
  getStudentSections: () => request("/students/sections"),
  discontinueStudent: (id: number, body: { Date?: string; Note?: string }) =>
    request(`/students/${id}/discontinue`, { method: "POST", body: JSON.stringify(body) }),
  completeStudent: (id: number, body: { Date?: string; Note?: string }) =>
    request(`/students/${id}/complete`, { method: "POST", body: JSON.stringify(body) }),
  restoreStudent: (id: number) => request(`/students/${id}/restore`, { method: "POST" }),
  promoteStudents: (body: { department_id?: number; dry_run: boolean; force?: boolean }) =>
    request("/students/promote", { method: "POST", body: JSON.stringify(body) }),
  createStudent: (payload: unknown) => request("/students", { method: "POST", body: JSON.stringify(payload) }),
  updateStudent: (id: number, payload: unknown) =>
    request(`/students/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deactivateStudent: (id: number) => request(`/students/${id}`, { method: "DELETE" }),
  // Students from Excel / CSV with column mapping (same flow as the employee import).
  studentImportInspect: async (file: File) => {
    const form = new FormData(); form.append("file", file);
    const token = getToken();
    const res = await fetch(`${BASE_URL}/students/import/inspect`, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json();
  },
  studentImportPreview: async (file: File, mapping: unknown) => {
    const form = new FormData(); form.append("file", file); form.append("mapping", JSON.stringify(mapping));
    const token = getToken();
    const res = await fetch(`${BASE_URL}/students/import/preview`, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json();
  },
  studentImportCommit: async (file: File, mapping: unknown) => {
    const form = new FormData(); form.append("file", file); form.append("mapping", JSON.stringify(mapping));
    const token = getToken();
    const res = await fetch(`${BASE_URL}/students/import/commit`, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form });
    if (!res.ok) throw new Error(await extractError(res));
    return res.json();
  },
  importStudents: (rows: unknown[]) =>
    request("/students/import", { method: "POST", body: JSON.stringify({ rows }) }),
  enrollStudentFromCamera: (code: string) =>
    request(`/students/${encodeURIComponent(code)}/enroll-from-camera`, { method: "POST" }),
  getStudentShifts: () => request("/student-shifts"),
  createStudentShift: (payload: unknown) => request("/student-shifts", { method: "POST", body: JSON.stringify(payload) }),
  updateStudentShift: (id: number, payload: unknown) =>
    request(`/student-shifts/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteStudentShift: (id: number) => request(`/student-shifts/${id}`, { method: "DELETE" }),
  getStudentLeaveTypes: () => request("/student-leaves/types"),
  createStudentLeaveType: (payload: unknown) =>
    request("/student-leaves/types", { method: "POST", body: JSON.stringify(payload) }),
  updateStudentLeaveType: (id: number, payload: unknown) =>
    request(`/student-leaves/types/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteStudentLeaveType: (id: number) => request(`/student-leaves/types/${id}`, { method: "DELETE" }),
  getStudentLeaveRequests: (p: { status?: string; department_id?: number; registered_year?: string } = {}) => {
    const s = new URLSearchParams();
    if (p.status) s.set("status", p.status);
    if (p.department_id) s.set("department_id", String(p.department_id));
    if (p.registered_year) s.set("registered_year", p.registered_year);
    return request(`/student-leaves/requests?${s.toString()}`);
  },
  createStudentLeaveRequest: (payload: unknown) =>
    request("/student-leaves/requests", { method: "POST", body: JSON.stringify(payload) }),
  decideStudentLeave: (id: number, status: "Approved" | "Rejected") =>
    request(`/student-leaves/requests/${id}/decision`, { method: "POST", body: JSON.stringify({ status }) }),
  /** Undo a student leave / OD; those days are recalculated. */
  cancelStudentLeave: (id: number) =>
    request(`/student-leaves/requests/${id}/cancel`, { method: "POST" }),
  getStudentDashboard: (p: { date: string; days: number; department_id?: number; registered_year?: string }) => {
    const s = new URLSearchParams({ date: p.date, days: String(p.days) });
    if (p.department_id) s.set("department_id", String(p.department_id));
    if (p.registered_year) s.set("registered_year", p.registered_year);
    return request(`/student-attendance/dashboard?${s.toString()}`);
  },
  getStudentDaily: (p: { date: string; department_id?: number; registered_year?: string }) => {
    const s = new URLSearchParams({ date: p.date });
    if (p.department_id) s.set("department_id", String(p.department_id));
    if (p.registered_year) s.set("registered_year", p.registered_year);
    return request(`/student-attendance/daily?${s.toString()}`);
  },
  markStudentAttendance: (payload: unknown) =>
    request("/student-attendance/manual", { method: "POST", body: JSON.stringify(payload) }),
  /** Same manual status for many students over a date range. */
  markStudentAttendanceBulk: (payload: { StudentCodes: string[]; FromDate: string; ToDate: string; Status: string; InTime?: string | null; OutTime?: string | null }) =>
    request("/student-attendance/manual/bulk", { method: "POST", body: JSON.stringify(payload) }),
  clearStudentManual: (student_code: string, date: string) =>
    request(`/student-attendance/manual?student_code=${encodeURIComponent(student_code)}&date=${date}`, { method: "DELETE" }),
  getStudentReport: (p: { from_date: string; to_date: string; department_id?: number; registered_year?: string; section?: string }) => {
    const s = new URLSearchParams({ from_date: p.from_date, to_date: p.to_date });
    if (p.department_id) s.set("department_id", String(p.department_id));
    if (p.registered_year) s.set("registered_year", p.registered_year);
    if (p.section) s.set("section", p.section);
    return request(`/student-attendance/report?${s.toString()}`);
  },
  downloadStudentReport: async (fmt: "csv" | "xlsx" | "pdf", p: { from_date: string; to_date: string; department_id?: number; registered_year?: string; section?: string }) => {
    const s = new URLSearchParams({ from_date: p.from_date, to_date: p.to_date });
    if (p.department_id) s.set("department_id", String(p.department_id));
    if (p.registered_year) s.set("registered_year", p.registered_year);
    if (p.section) s.set("section", p.section);
    const token = getToken();
    const res = await fetch(`${BASE_URL}/student-attendance/report/export.${fmt}?${s.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Export failed (${res.status})`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `student_attendance_${p.from_date}_${p.to_date}.${fmt}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  // ---- Organization branding / address ----
  getOrganization: () => request("/settings/organization"),
  updateOrganization: (payload: Record<string, string>) =>
    request("/settings/organization", { method: "PUT", body: JSON.stringify(payload) }),

  // Attendance categories
  getCategories: () => request("/categories"),
  getCategory: (id: number) => request(`/categories/${id}`),
  createCategory: (payload: unknown) =>
    request("/categories", { method: "POST", body: JSON.stringify(payload) }),
  updateCategory: (id: number, payload: unknown) =>
    request(`/categories/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteCategory: (id: number) => request(`/categories/${id}`, { method: "DELETE" }),

  // Shifts configuration
  getShifts: () => request("/shifts"),
  createShift: (payload: unknown) => request("/shifts", { method: "POST", body: JSON.stringify(payload) }),
  updateShift: (id: number, payload: unknown) =>
    request(`/shifts/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteShift: (id: number) => request(`/shifts/${id}`, { method: "DELETE" }),

  // Rosters configuration
  getRosters: (employeeCode?: string) =>
    request(employeeCode ? `/rosters?employee_code=${encodeURIComponent(employeeCode)}` : "/rosters"),
  createRoster: (payload: unknown) => request("/rosters", { method: "POST", body: JSON.stringify(payload) }),
  updateRoster: (id: number, payload: unknown) =>
    request(`/rosters/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteRoster: (id: number) => request(`/rosters/${id}`, { method: "DELETE" }),
  assignShift: (payload: { EmployeeCodes: string[]; ShiftId: number; FromDate: string; ToDate?: string | null }) =>
    request("/rosters/assign", { method: "POST", body: JSON.stringify(payload) }),

  // Holidays configuration
  getHolidays: (year?: number) =>
    request(year ? `/holidays?year=${year}` : "/holidays"),
  createHoliday: (payload: unknown) =>
    request("/holidays", { method: "POST", body: JSON.stringify(payload) }),
  updateHoliday: (id: number, payload: unknown) =>
    request(`/holidays/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteHoliday: (id: number) => request(`/holidays/${id}`, { method: "DELETE" }),

  // Leave configuration
  getLeaveConfigs: () => request("/leave-config"),
  createLeaveConfig: (payload: unknown) =>
    request("/leave-config", { method: "POST", body: JSON.stringify(payload) }),
  updateLeaveConfig: (id: number, payload: unknown) =>
    request(`/leave-config/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteLeaveConfig: (id: number) => request(`/leave-config/${id}`, { method: "DELETE" }),

  // ESS – My Leaves
  getMyLeaves: (params: { employee_code: string; from_date?: string; to_date?: string }) => {
    const search = new URLSearchParams();
    search.set("employee_code", params.employee_code);
    if (params.from_date) search.set("from_date", params.from_date);
    if (params.to_date) search.set("to_date", params.to_date);
    const qs = search.toString();
    return request(`/leaves/my?${qs}`);
  },
  getLeaveBalance: (employeeCode: string, year?: number) => {
    const search = new URLSearchParams();
    search.set("employee_code", employeeCode);
    if (year) search.set("year", String(year));
    return request(`/leaves/balance?${search.toString()}`);
  },
  applyLeave: (payload: unknown) =>
    request("/leaves/apply", { method: "POST", body: JSON.stringify(payload) }),
  /** Admin enters a leave directly: saved as Approved, no approval steps. */
  adminLeaveEntry: (payload: unknown) =>
    request("/leaves/admin-entry", { method: "POST", body: JSON.stringify(payload) }),
  /** Admin undoes a leave; its days go back to the balance. */
  cancelLeave: (leaveRequestId: number) =>
    request(`/leaves/${leaveRequestId}/cancel`, { method: "POST" }),

  // ESS – Manual Entry / OD
  getMyManualEntries: (params: { employee_code: string; from_date?: string; to_date?: string }) => {
    const search = new URLSearchParams();
    search.set("employee_code", params.employee_code);
    if (params.from_date) search.set("from_date", params.from_date);
    if (params.to_date) search.set("to_date", params.to_date);
    const qs = search.toString();
    return request(`/manual-entries/my?${qs}`);
  },
  applyManualEntry: (payload: unknown) =>
    request("/manual-entries/apply", { method: "POST", body: JSON.stringify(payload) }),
  updateManualEntry: (id: number, payload: unknown) =>
    request(`/manual-entries/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteManualEntry: (id: number) =>
    request(`/manual-entries/${id}`, { method: "DELETE" }),

  // Role config (User Roles)
  getRoleConfig: () => request("/role-config"),
  updateRoleConfig: (payload: { admin: Record<string, boolean>; manager: Record<string, boolean>; employee: Record<string, boolean> }) =>
    request("/role-config", { method: "PUT", body: JSON.stringify(payload) }),
  /** Campus roles: a role limited to one institution, with its own menu switches. */
  getCampusRoles: () => request("/role-config/campus-roles"),
  saveCampusRole: (payload: { name: string; organization_id: number | null; device_ids?: number[]; permissions: Record<string, boolean>; original_name?: string | null }) =>
    request("/role-config/campus-roles", { method: "PUT", body: JSON.stringify(payload) }),
  deleteCampusRole: (name: string) => request(`/role-config/campus-roles/${encodeURIComponent(name)}`, { method: "DELETE" }),
  /** The signed-in login: role, and for a campus role its institution and menus. */
  getMe: () => request("/auth/me"),

  createUser: (payload: { login_name: string; password: string; role_name?: string; employee_code?: string }) =>
    request("/users", { method: "POST", body: JSON.stringify(payload) }),
  getLogins: () => request("/users/logins"),
  blockLogin: (payload: { login_name: string; blocked: boolean }) =>
    request("/users/block", { method: "POST", body: JSON.stringify(payload) }),
  resetPassword: (payload: { login_name: string; new_password: string }) =>
    request("/users/reset-password", { method: "POST", body: JSON.stringify(payload) }),

  // ---- Face recognition attendance (camera_service) ----
  enrollFace: async (employeeCode: string, photo: File) => {
    // Multipart upload — don't set Content-Type, the browser adds the boundary.
    const token = getToken();
    const form = new FormData();
    form.append("photo", photo);
    const res = await fetch(`${BASE_URL}/face/enroll/${encodeURIComponent(employeeCode)}`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const parsed = await res.json();
        if (typeof parsed?.detail === "string") detail = parsed.detail;
      } catch { /* keep default */ }
      throw new Error(detail);
    }
    return res.json();
  },
  enrollFaceFromCamera: (employeeCode: string) =>
    request(`/face/enroll-from-camera/${encodeURIComponent(employeeCode)}`, { method: "POST" }),
  // Capture the live camera frame + quality, WITHOUT enrolling (preview step).
  previewCameraFrame: () => request("/face/preview-camera"),
  // Quality of an uploaded photo, WITHOUT enrolling (preview step).
  previewPhoto: async (photo: File) => {
    const token = getToken();
    const form = new FormData();
    form.append("photo", photo);
    const res = await fetch(`${BASE_URL}/face/preview-photo`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { const p = await res.json(); if (typeof p?.detail === "string") detail = p.detail; } catch { /* keep */ }
      throw new Error(detail);
    }
    return res.json();
  },
  getFaceEnrollmentSummary: () => request("/face/enrollments"),
  getFaceEnrollments: (employeeCode: string) =>
    request(`/face/enrollments/${encodeURIComponent(employeeCode)}`),
  deleteFaceEnrollment: (embeddingId: number) =>
    request(`/face/enrollments/${embeddingId}`, { method: "DELETE" }),
  getCameraStatus: () => request("/face/camera-status"),
  getFacePunches: (limit = 20) => request(`/face/punches?limit=${limit}`),
};
