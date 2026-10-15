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

// ---------------------------------------------------------------------------------------------------------------
// Campus roles: a role limited to ONE institution (e.g. "Campus 2" -> Engineering Campus Staff). Unlike the built-in
// roles above, these ARE applied: a login with a campus role sees only its institution's devices, employees and
// reports (enforced by the server) and only the menus switched on here.
// ---------------------------------------------------------------------------------------------------------------
type CampusRole = { name: string; organization_id: number | null; permissions: Record<string, boolean> };

const CAMPUS_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  employees: "Employees (manage, own institution)",
  devices: "Devices (own institution)",
  enrollment: "Enrollment / Face attendance",
  transfer: "Transfer",
  commands: "Commands",
  logs: "Attendance Logs",
  reports: "All reports",
  leave_entry: "Leave Entry (approved at once)",
  leave_approvals: "Leave Approvals",
  ess_attendance: "ESS – My Attendance",
  ess_leaves: "ESS – My Leaves",
  ess_manual_entry: "ESS – Manual Entry / OD",
};
// One-click starting points for a new custom role.
const PRESETS: { label: string; perms: string[] }[] = [
  { label: "Reports + Leave Entry (Leave Section)", perms: ["reports", "leave_entry"] },
  { label: "Admin's daily menus (campus)", perms: ["dashboard", "employees", "devices", "enrollment", "transfer", "commands", "logs", "reports", "leave_entry", "ess_attendance", "ess_leaves", "ess_manual_entry"] },
];

const CAMPUS_GROUPS: { title: string; desc: string; keys: string[] }[] = [
  { title: "Devices and staff", desc: "Only this institution", keys: ["dashboard", "employees", "devices", "enrollment", "transfer", "commands"] },
  { title: "Reports and leave", desc: "Only this institution's staff", keys: ["logs", "reports", "leave_entry", "leave_approvals"] },
  { title: "ESS portal", desc: "Self-service pages", keys: ["ess_attendance", "ess_leaves", "ess_manual_entry"] },
];

function CampusRoleEditor({ role, isNew, organizations, defaults, onSaved, onDeleted }: {
  role: CampusRole | null;
  isNew: boolean;
  organizations: { OrganizationId: number; OrgName: string }[];
  defaults: Record<string, boolean>;
  onSaved: (saved: CampusRole) => void;
  onDeleted: (name: string) => void;
}) {
  const start = () => ({
    name: role?.name ?? "",
    organization_id: role?.organization_id ?? null,
    permissions: { ...defaults, ...(role?.permissions ?? {}) },
  });
  const [form, setForm] = useState(start);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { setForm(start()); setMsg(null); }, [role?.name, isNew]);  // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!form.name.trim()) { setMsg({ ok: false, text: "Give the role a name, e.g. Campus 2 or Leave Section." }); return; }
    setBusy(true); setMsg(null);
    try {
      const saved = await api.saveCampusRole({
        name: form.name.trim(), organization_id: form.organization_id, permissions: form.permissions,
        original_name: isNew ? null : role?.name ?? null,
      });
      setMsg({ ok: true, text: `Saved. Give a login the role "${saved.name}" (Employees → Portal login) to use it.` });
      onSaved(saved);
    } catch (e: any) {
      setMsg({ ok: false, text: e?.message || "Save failed." });
    } finally { setBusy(false); }
  };

  const remove = async () => {
    if (!role || !window.confirm(`Delete the role "${role.name}"? Logins must be moved to another role first.`)) return;
    setBusy(true); setMsg(null);
    try { await api.deleteCampusRole(role.name); onDeleted(role.name); }
    catch (e: any) { setMsg({ ok: false, text: e?.message || "Delete failed." }); }
    finally { setBusy(false); }
  };

  const setPerm = (k: string, v: boolean) => setForm((f) => ({ ...f, permissions: { ...f.permissions, [k]: v } }));
  const orgName = organizations.find((o) => o.OrganizationId === form.organization_id)?.OrgName;
  const applyPreset = (perms: string[]) =>
    setForm((f) => ({ ...f, permissions: Object.fromEntries(Object.keys(CAMPUS_LABELS).map((k) => [k, perms.includes(k)])) }));

  return (
    <>
      <p className="roles-blurb">
        {form.organization_id
          ? <>Limited to <strong>{orgName || "one institution"}</strong>: logins with this role see only that institution's devices, employees and reports.</>
          : <>For <strong>all institutions</strong>.</>}{" "}
        They see only the menus switched on below; students and configuration are never shown to this role.
      </p>
      <div className="section-card" style={{ marginBottom: 16 }}>
        <div className="form-row-2">
          <label><span>Role name</span>
            <input value={form.name} maxLength={50} placeholder="e.g. Campus 2" onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label><span>Institution</span>
            <select value={form.organization_id ?? ""} onChange={(e) => setForm({ ...form, organization_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">All institutions</option>
              {organizations.map((o) => <option key={o.OrganizationId} value={o.OrganizationId}>{o.OrgName}</option>)}
            </select>
          </label>
        </div>
      </div>
      <div className="roles-presets">
        <span>Start from:</span>
        {PRESETS.map((p) => (
          <button key={p.label} type="button" className="btn-device-ghost" onClick={() => applyPreset(p.perms)}>{p.label}</button>
        ))}
      </div>
      <div className="roles-grid">
        {CAMPUS_GROUPS.map((g) => {
          const on = g.keys.filter((k) => form.permissions[k]).length;
          return (
            <section key={g.title} className="section-card roles-card" aria-labelledby={`cgrp-${g.title}`}>
              <header className="roles-card-head">
                <div>
                  <h3 id={`cgrp-${g.title}`}>{g.title}</h3>
                  <p>{g.desc} · {on}/{g.keys.length}</p>
                </div>
              </header>
              <div className="switch-list" style={{ marginTop: 0, paddingTop: 0, borderTop: 0 }}>
                {g.keys.map((k) => (
                  <SwitchRow key={k} id={`cperm-${k}`} checked={!!form.permissions[k]} onChange={(v) => setPerm(k, v)} title={CAMPUS_LABELS[k]} />
                ))}
              </div>
            </section>
          );
        })}
      </div>
      <div className="roles-bar is-dirty">
        <span className="roles-bar-text">
          {msg ? <span className={msg.ok ? "note-ok" : "note-err"} style={{ margin: 0, fontWeight: 600 }} role="status">{msg.text}</span>
            : isNew ? "New role" : `Role "${role?.name}"`}
        </span>
        {!isNew && <button type="button" className="btn btn-outline-reports" onClick={remove} disabled={busy}>Delete role</button>}
        <button type="button" className="btn btn-primary-purple" onClick={save} disabled={busy}>{busy ? "Saving…" : isNew ? "Create role" : "Save role"}</button>
      </div>
    </>
  );
}

export function UserRolesConfigPage() {
  const [campusRoles, setCampusRoles] = useState<CampusRole[]>([]);
  const [campusDefaults, setCampusDefaults] = useState<Record<string, boolean>>({});
  const [organizations, setOrganizations] = useState<{ OrganizationId: number; OrgName: string }[]>([]);
  const [campusSel, setCampusSel] = useState<string | null>(null);   // a campus role name, "__new__", or null
  useEffect(() => {
    api.getCampusRoles().then((r: any) => { setCampusRoles(r.roles || []); setCampusDefaults(r.default_permissions || {}); }).catch(() => {});
    api.getOrganizations().then(setOrganizations).catch(() => setOrganizations([]));
  }, []);
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
        <strong>Heads up.</strong> Admin, Manager and Employee switches are saved but not yet applied to menus.
        <strong> Roles added with "+ New role" are applied:</strong> they see only the menus switched on, and a role set to one institution sees only that institution.
      </div>

      {loadError && <p className="note-err">{loadError}</p>}

      <div className="roles-tabs">
        <Segmented label="Role" value={campusSel ? "" : role} onChange={(v) => { setCampusSel(null); setRole(v as RoleId); }}
          options={(Object.keys(ROLE_META) as RoleId[]).map((r) => [r, ROLE_META[r].label] as [string, string])} />
        {campusRoles.map((c) => (
          <button key={c.name} type="button" className={"roles-campus-tab" + (campusSel === c.name ? " is-on" : "")}
            aria-pressed={campusSel === c.name} onClick={() => setCampusSel(c.name)}>
            {c.name}
            <small>{c.organization_id ? (organizations.find((o) => o.OrganizationId === c.organization_id)?.OrgName || "one institution") : "All institutions"}</small>
          </button>
        ))}
        <button type="button" className={"roles-campus-new" + (campusSel === "__new__" ? " is-on" : "")} onClick={() => setCampusSel("__new__")}>
          + New role
        </button>
        {!campusSel && <span className="roles-count"><b>{allowed}</b> of {meta.keys.length} allowed</span>}
      </div>

      {campusSel ? (
        <CampusRoleEditor
          role={campusSel === "__new__" ? null : campusRoles.find((c) => c.name === campusSel) ?? null}
          isNew={campusSel === "__new__"}
          organizations={organizations}
          defaults={campusDefaults}
          onSaved={(saved) => {
            setCampusRoles((list) => [...list.filter((c) => c.name !== saved.name && c.name !== campusSel), saved]
              .sort((a, b) => a.name.localeCompare(b.name)));
            setCampusSel(saved.name);
          }}
          onDeleted={(name) => { setCampusRoles((list) => list.filter((c) => c.name !== name)); setCampusSel(null); }}
        />
      ) : <>
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
      </>}
    </div>
  );
}
