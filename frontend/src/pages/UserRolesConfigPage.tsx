import { useState, useCallback, useEffect, useMemo } from "react";
import { api } from "../api/client";
import { Segmented, SwitchRow } from "../components/ConfigUi";

export type RoleId = "admin" | "manager" | "employee";

export type PermissionKey =
  | "dashboard"
  | "devices"
  | "employees"
  | "enrollment"
  | "transfer"
  | "commands"
  | "logs"
  | "logs_view_own"
  | "ess_attendance"
  | "ess_leaves"
  | "ess_manual_entry"
  | "config_shifts"
  | "config_rosters"
  | "config_holidays"
  | "config_leaves"
  | "config_categories"
  | "user_roles";

const PERMISSION_LABELS: Record<PermissionKey, string> = {
  dashboard: "Dashboard",
  devices: "Devices (manage)",
  employees: "Employees (manage)",
  enrollment: "Enrollment",
  transfer: "Transfer",
  commands: "Commands",
  logs: "Attendance Logs",
  logs_view_own: "View own attendance logs only",
  ess_attendance: "ESS – My Attendance",
  ess_leaves: "ESS – My Leaves",
  ess_manual_entry: "ESS – Manual Entry / OD",
  config_shifts: "Config – Shifts",
  config_rosters: "Config – Rosters",
  config_holidays: "Config – Holidays",
  config_leaves: "Config – Leave Types",
  config_categories: "Config – Categories",
  user_roles: "User & role management",
};

const ADMIN_PERMISSIONS: PermissionKey[] = [
  "dashboard",
  "devices",
  "employees",
  "enrollment",
  "transfer",
  "commands",
  "logs",
  "ess_attendance",
  "ess_leaves",
  "ess_manual_entry",
  "config_shifts",
  "config_rosters",
  "config_holidays",
  "config_leaves",
  "config_categories",
  "user_roles",
];

const MANAGER_PERMISSIONS: PermissionKey[] = [
  "dashboard",
  "devices",
  "employees",
  "enrollment",
  "transfer",
  "commands",
  "logs",
  "ess_attendance",
  "ess_leaves",
  "ess_manual_entry",
  "config_shifts",
  "config_rosters",
  "config_holidays",
  "config_leaves",
  "config_categories",
];

const EMPLOYEE_PERMISSIONS: PermissionKey[] = [
  "ess_attendance",
  "ess_leaves",
  "ess_manual_entry",
  "logs_view_own",
];

function defaultPermissions(role: RoleId): Record<PermissionKey, boolean> {
  const all = PERMISSION_LABELS as Record<PermissionKey, string>;
  const base: Record<string, boolean> = {};
  for (const k of Object.keys(all) as PermissionKey[]) {
    base[k] = false;
  }
  if (role === "admin") {
    ADMIN_PERMISSIONS.forEach((k) => (base[k] = true));
  } else if (role === "manager") {
    MANAGER_PERMISSIONS.forEach((k) => (base[k] = true));
  } else if (role === "employee") {
    EMPLOYEE_PERMISSIONS.forEach((k) => (base[k] = true));
  }
  return base as Record<PermissionKey, boolean>;
}

function buildInitialState(): Record<RoleId, Record<PermissionKey, boolean>> {
  return {
    admin: defaultPermissions("admin"),
    manager: defaultPermissions("manager"),
    employee: defaultPermissions("employee"),
  };
}

function mergeRoleConfig(
  fromApi: Record<string, Record<string, boolean>>
): Record<RoleId, Record<PermissionKey, boolean>> {
  const defaults = buildInitialState();
  const roles: RoleId[] = ["admin", "manager", "employee"];
  const keys = Object.keys(PERMISSION_LABELS) as PermissionKey[];
  const out = { ...defaults };
  for (const role of roles) {
    const apiRole = fromApi[role];
    if (!apiRole || typeof apiRole !== "object") continue;
    const merged = { ...defaults[role] };
    for (const k of keys) {
      if (typeof apiRole[k] === "boolean") merged[k] = apiRole[k];
    }
    out[role] = merged;
  }
  return out;
}

const ROLE_META: Record<RoleId, { label: string; blurb: string; keys: PermissionKey[] }> = {
  admin: { label: "Admin", blurb: "Full system access, including user and role management.", keys: ADMIN_PERMISSIONS },
  manager: { label: "Manager", blurb: "Runs devices, staff, configuration and reports. No user or role management.", keys: MANAGER_PERMISSIONS },
  employee: { label: "Employee", blurb: "Self-service only: the ESS portal and their own attendance logs.", keys: EMPLOYEE_PERMISSIONS },
};

const GROUPS: { title: string; desc: string; keys: PermissionKey[] }[] = [
  { title: "Devices and staff", desc: "Daily operations", keys: ["dashboard", "devices", "employees", "enrollment", "transfer", "commands", "logs"] },
  { title: "ESS portal", desc: "Self-service pages", keys: ["ess_attendance", "ess_leaves", "ess_manual_entry"] },
  { title: "Configuration", desc: "Rules and masters", keys: ["config_shifts", "config_rosters", "config_holidays", "config_leaves", "config_categories"] },
  { title: "Administration", desc: "Users and roles", keys: ["user_roles"] },
  { title: "Own data", desc: "Limit what they can see", keys: ["logs_view_own"] },
];

export function UserRolesConfigPage() {
  const [permissions, setPermissions] = useState(buildInitialState);
  const [saved, setSaved] = useState(() => JSON.stringify(buildInitialState()));
  const [role, setRole] = useState<RoleId>("admin");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    api
      .getRoleConfig()
      .then((data: unknown) => {
        if (cancelled) return;
        const raw = data as Record<string, Record<string, boolean>>;
        if (raw && (raw.admin || raw.manager || raw.employee)) {
          const merged = mergeRoleConfig(raw);
          setPermissions(merged);
          setSaved(JSON.stringify(merged));
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Failed to load role config");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const dirty = useMemo(() => JSON.stringify(permissions) !== saved, [permissions, saved]);

  const setRolePermission = useCallback((r: RoleId, key: PermissionKey, value: boolean) => {
    setSaveMessage(null);
    setPermissions((prev) => ({ ...prev, [r]: { ...prev[r], [key]: value } }));
  }, []);

  const setMany = useCallback((r: RoleId, keys: PermissionKey[], value: boolean) => {
    setSaveMessage(null);
    setPermissions((prev) => {
      const next = { ...prev[r] };
      keys.forEach((k) => (next[k] = value));
      return { ...prev, [r]: next };
    });
  }, []);

  const handleUpdate = useCallback(() => {
    setSaveMessage(null);
    setSaving(true);
    api
      .updateRoleConfig(permissions)
      .then(() => {
        setSaved(JSON.stringify(permissions));
        setSaveMessage({ type: "success", text: "Role permissions saved." });
      })
      .catch((err: unknown) =>
        setSaveMessage({ type: "error", text: err instanceof Error ? err.message : "Failed to save" })
      )
      .finally(() => setSaving(false));
  }, [permissions]);

  const discard = () => { setPermissions(JSON.parse(saved)); setSaveMessage(null); };

  const meta = ROLE_META[role];
  const allowed = meta.keys.filter((k) => permissions[role][k]).length;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>User Roles</h2>
          <p className="sub">Choose what Admin, Manager and Employee are allowed to open. Pick a role, adjust its switches, then save.</p>
        </div>
      </div>

      <div className="roles-note" role="note">
        <strong>Heads up.</strong> These permissions are saved, but the app does not restrict menus or pages by role yet.
        Treat this as the access plan for now.
      </div>

      {loadError && <p className="note-err">{loadError}</p>}

      <div className="roles-tabs">
        <Segmented label="Role" value={role} onChange={(v) => setRole(v as RoleId)}
          options={(Object.keys(ROLE_META) as RoleId[]).map((r) => [r, ROLE_META[r].label] as [string, string])} />
        <span className="roles-count"><b>{allowed}</b> of {meta.keys.length} allowed</span>
      </div>
      <p className="roles-blurb">{meta.blurb}</p>

      <div className="roles-grid">
        {GROUPS.map((g) => {
          const keys = g.keys.filter((k) => meta.keys.includes(k));
          if (keys.length === 0) return null;
          const on = keys.filter((k) => permissions[role][k]).length;
          return (
            <section key={g.title} className="section-card roles-card" aria-labelledby={`grp-${g.title}`}>
              <header className="roles-card-head">
                <div>
                  <h3 id={`grp-${g.title}`}>{g.title}</h3>
                  <p>{g.desc} · {on}/{keys.length}</p>
                </div>
                {keys.length > 1 && (
                  <button type="button" className="notif-link" onClick={() => setMany(role, keys, on !== keys.length)}>
                    {on === keys.length ? "Clear all" : "Allow all"}
                  </button>
                )}
              </header>
              <div className="switch-list" style={{ marginTop: 0, paddingTop: 0, borderTop: 0 }}>
                {keys.map((key) => (
                  <SwitchRow key={key} id={`perm-${role}-${key}`} checked={permissions[role][key] ?? false}
                    onChange={(v) => setRolePermission(role, key, v)} title={PERMISSION_LABELS[key]} />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      <div className={"roles-bar" + (dirty ? " is-dirty" : "")}>
        <span className="roles-bar-text">
          {saveMessage
            ? <span className={saveMessage.type === "success" ? "note-ok" : "note-err"} style={{ margin: 0, fontWeight: 600 }} role="status">{saveMessage.text}</span>
            : dirty ? "You have unsaved changes" : "All changes saved"}
        </span>
        <button type="button" className="btn btn-outline-reports" onClick={discard} disabled={!dirty || saving}>Discard</button>
        <button type="button" className="btn btn-primary-purple" onClick={handleUpdate} disabled={!dirty || saving}>{saving ? "Saving…" : "Save changes"}</button>
      </div>
    </div>
  );
}
