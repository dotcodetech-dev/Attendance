import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";

import { NotificationBell } from "./NotificationBell";
import { Icons } from "./SidebarIcons";
import { api, CONNECTION_ISSUE_EVENT, CONNECTION_OK_EVENT, SESSION_EXPIRED_EVENT } from "../api/client";
import { clearToken, getUsername } from "../store/auth";
import { Features, FeaturesProvider, useFeatures } from "../store/features";
import { MeProvider, useMe } from "../store/me";
import { OrgProvider, useOrg } from "../store/org";

type NavEntry = { to: string; icon: React.ReactNode; label: string };
type NavGroup = { key: string; label: string; items: NavEntry[] };

// Single source of truth for the sidebar AND page titles.
const TOP_ITEMS: NavEntry[] = [
  { to: "/", icon: Icons.dashboard, label: "Dashboard" },
  { to: "/employees", icon: Icons.employees, label: "Employees" },
];

const NAV_GROUPS: NavGroup[] = [
  {
    key: "devices",
    label: "Device Management",
    items: [
      { to: "/devices", icon: Icons.devices, label: "Devices" },
      { to: "/enrollment", icon: Icons.enrollment, label: "Enrollment" },
      { to: "/face", icon: Icons.user, label: "Face Attendance" },
      { to: "/transfer", icon: Icons.transfer, label: "Transfer" },
      { to: "/commands", icon: Icons.commands, label: "Commands" },
    ],
  },
  {
    key: "reports",
    label: "Reports",
    items: [
      { to: "/logs", icon: Icons.logs, label: "Attendance Logs" },
      { to: "/reports/daily", icon: Icons.user, label: "Present / Absent" },
      { to: "/reports/muster-time", icon: Icons.calendar, label: "Attendance (Time)" },
      { to: "/reports/muster-leave", icon: Icons.calendar, label: "Attendance (Time & Leave)" },
      { to: "/reports/register", icon: Icons.calendar, label: "Monthly Register" },
      { to: "/reports/late-arrival", icon: Icons.logs, label: "Late Arrival" },
      { to: "/reports/early-departure", icon: Icons.logs, label: "Early Departure" },
      { to: "/reports/in-out", icon: Icons.logs, label: "In-Out List" },
      { to: "/reports/employee-list", icon: Icons.user, label: "Employee List" },
      { to: "/reports/leave-balance", icon: Icons.document, label: "Leave Balance" },
      { to: "/reports/late-ot", icon: Icons.logs, label: "Late / Early" },
      { to: "/reports/individual", icon: Icons.calendar, label: "Individual Sheet" },
    ],
  },
  {
    key: "mess",
    label: "Mess",
    items: [
      { to: "/mess/token", icon: Icons.tag, label: "Mess Token" },
      { to: "/mess/kiosk", icon: Icons.devices, label: "Mess Kiosk" },
      { to: "/mess/report", icon: Icons.document, label: "Token Report" },
    ],
  },
  {
    key: "ess",
    label: "ESS Portal",
    items: [
      { to: "/ess/my-attendance", icon: Icons.calendar, label: "My Attendance" },
      { to: "/ess/my-leaves", icon: Icons.leaves, label: "My Leaves" },
      { to: "/ess/leave-approvals", icon: Icons.roles, label: "Leave Approvals" },
      { to: "/ess/leave-entry", icon: Icons.leaves, label: "Leave Entry (Admin)" },
      { to: "/ess/manual-entry", icon: Icons.edit, label: "Manual Entry / OD" },
    ],
  },
  {
    key: "config",
    label: "Configuration",
    items: [
      { to: "/config/shifts", icon: Icons.shift, label: "Shifts" },
      { to: "/config/attendance-rules", icon: Icons.logs, label: "Attendance Rules" },
      { to: "/config/rosters", icon: Icons.roster, label: "Rosters" },
      { to: "/config/holidays", icon: Icons.holiday, label: "Holidays" },
      { to: "/config/leaves", icon: Icons.document, label: "Leave Types" },
      { to: "/config/categories", icon: Icons.tag, label: "Categories" },
      { to: "/config/roles", icon: Icons.roles, label: "User Roles" },
      { to: "/config/organization", icon: Icons.document, label: "Organization" },
      { to: "/config/masters", icon: Icons.tag, label: "Org & Masters" },
      { to: "/config/mess", icon: Icons.tag, label: "Module Configuration" },
    ],
  },
];

// Shown only when the Student Attendance provision is enabled (Canteen Settings).
const STUDENT_GROUP: NavGroup = {
  key: "students",
  label: "Students",
  items: [
    { to: "/students/dashboard", icon: Icons.dashboard, label: "Student Dashboard" },
    { to: "/students", icon: Icons.employees, label: "Students" },
    { to: "/students/attendance", icon: Icons.calendar, label: "Student Attendance" },
    { to: "/students/shifts", icon: Icons.shift, label: "Student Shifts" },
    { to: "/students/leaves", icon: Icons.leaves, label: "Student Manual Marking" },
    { to: "/students/reports", icon: Icons.document, label: "Student Report" },
  ],
};

// A module that is switched off in Module Configuration has no menu at all.
// (Module Configuration itself lives under Configuration and is always shown.)
const visibleGroups = (features: Features): NavGroup[] => {
  const groups = NAV_GROUPS.filter((g) => g.key !== "mess" || features.mess_tokens);
  if (!features.student_attendance) return groups;
  const anchor = groups.findIndex((g) => g.key === (features.mess_tokens ? "mess" : "reports"));
  const at = anchor >= 0 ? anchor + 1 : groups.length;
  // Student Leaves is a sub-option of Student Attendance with its own switch.
  const students: NavGroup = {
    ...STUDENT_GROUP,
    items: STUDENT_GROUP.items.filter((i) => i.to !== "/students/leaves" || features.student_leaves),
  };
  return [...groups.slice(0, at), students, ...groups.slice(at)];
};

// Permission switch (User Roles) behind each menu. Only a campus role is limited by them; Admin, Manager and
// Employee keep every menu, as before. Keys a campus role does not list (configuration, students, mess) stay hidden.
function permOf(path: string): string {
  if (path === "/") return "dashboard";
  if (path === "/employees") return "employees";
  if (path === "/devices") return "devices";
  if (path === "/enrollment" || path === "/face") return "enrollment";
  if (path === "/transfer") return "transfer";
  if (path === "/commands") return "commands";
  if (path === "/logs") return "logs";
  if (path.startsWith("/reports/")) return "reports";
  if (path === "/ess/my-attendance") return "ess_attendance";
  if (path === "/ess/my-leaves") return "ess_leaves";
  if (path === "/ess/leave-approvals") return "leave_approvals";
  if (path === "/ess/leave-entry") return "leave_entry";
  if (path === "/ess/manual-entry") return "ess_manual_entry";
  if (path.startsWith("/students")) return "students";
  if (path.startsWith("/mess")) return "mess";
  return "config";
}

const TITLE_BY_PATH: Record<string, string> = (() => {
  const map: Record<string, string> = {};
  TOP_ITEMS.forEach((i) => (map[i.to] = i.label));
  [...NAV_GROUPS, STUDENT_GROUP].forEach((g) => g.items.forEach((i) => (map[i.to] = i.label)));
  return map;
})();

const GROUP_OF_PATH: Record<string, string> = (() => {
  const map: Record<string, string> = {};
  [...NAV_GROUPS, STUDENT_GROUP].forEach((g) => g.items.forEach((i) => (map[i.to] = g.key)));
  return map;
})();

function PageTitle() {
  const { pathname } = useLocation();
  const title = TITLE_BY_PATH[pathname] ?? "Dashboard";
  return (
    <>
      <h1>{title}</h1>
      <p>Enterprise biometric device management platform</p>
    </>
  );
}

const chevron = (
  <svg className="nav-group-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

function NavItem({ to, icon, children }: { to: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <NavLink to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
      <span className="sidebar-nav-icon">{icon}</span>
      <span>{children}</span>
    </NavLink>
  );
}

function ProfileMenu({ onLogout }: { onLogout: () => void }) {
  const username = getUsername() || "Administrator";
  const { me } = useMe();
  const roleLine = me?.campus
    ? `${me.campus.role} · ${me.campus.organization_id ? (me.campus.organization_name || "one institution") : "All institutions"}`
    : me?.role ? `Signed in · ${me.role}` : "Signed in";
  const initial = username.charAt(0).toUpperCase();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
        setEditing(false);
        setMsg(null);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const savePassword = async () => {
    setMsg(null);
    if (pwd.length < 4) {
      setMsg({ text: "Password must be at least 4 characters.", ok: false });
      return;
    }
    if (pwd !== confirm) {
      setMsg({ text: "Passwords do not match.", ok: false });
      return;
    }
    setSaving(true);
    try {
      await api.resetPassword({ login_name: username, new_password: pwd });
      setMsg({ text: "Password updated successfully.", ok: true });
      setPwd("");
      setConfirm("");
      setEditing(false);
    } catch (err) {
      setMsg({ text: `Update failed: ${(err as Error).message}`, ok: false });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="profile-menu-wrap" ref={wrapRef}>
      <button
        type="button"
        className="topbar-icon-btn profile-trigger"
        aria-label="Profile"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="profile-avatar">{initial}</span>
      </button>

      {open && (
        <div className="profile-dropdown" role="menu">
          <div className="profile-dropdown-head">
            <span className="profile-avatar lg">{initial}</span>
            <div>
              <div className="profile-name">{username}</div>
              <div className="profile-role">{roleLine}</div>
            </div>
          </div>

          {!editing ? (
            <div className="profile-dropdown-body">
              <button type="button" className="profile-item" onClick={() => { setEditing(true); setMsg(null); }}>
                <span className="sidebar-nav-icon">{Icons.edit}</span>
                <span>Edit profile / password</span>
              </button>
              <button type="button" className="profile-item danger" onClick={onLogout}>
                <span className="sidebar-nav-icon">{Icons.logout}</span>
                <span>Logout</span>
              </button>
            </div>
          ) : (
            <div className="profile-edit">
              <label className="profile-field">
                <span>Username</span>
                <input value={username} disabled />
              </label>
              <label className="profile-field">
                <span>New password</span>
                <input type="password" value={pwd} placeholder="Enter new password"
                  onChange={(e) => setPwd(e.target.value)} />
              </label>
              <label className="profile-field">
                <span>Confirm password</span>
                <input type="password" value={confirm} placeholder="Re-enter new password"
                  onChange={(e) => setConfirm(e.target.value)} />
              </label>
              <div className="profile-edit-actions">
                <button type="button" className="btn-device-ghost" onClick={() => { setEditing(false); setPwd(""); setConfirm(""); setMsg(null); }}>
                  Cancel
                </button>
                <button type="button" className="btn-device-purple" disabled={saving} onClick={savePassword}>
                  {saving ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          )}

          {msg && <p className={`profile-msg ${msg.ok ? "ok" : "err"}`}>{msg.text}</p>}
        </div>
      )}
    </div>
  );
}

export function Layout() {
  return (
    <OrgProvider>
      <FeaturesProvider>
        <MeProvider>
          <LayoutInner />
        </MeProvider>
      </FeaturesProvider>
    </OrgProvider>
  );
}

function LayoutInner() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { org } = useOrg();
  const logout = () => {
    clearToken();
    navigate("/login");
  };

  // Any API call that comes back 401 means the session is no longer valid (expired, or the
  // server restarted with a different signing key). Previously every page just swallowed that
  // as "no data" and stayed stuck until someone noticed and logged out/in by hand. Now it sends
  // them straight to Login with a reason, the same fix applied automatically.
  useEffect(() => {
    const onExpired = () => {
      sessionStorage.setItem("sessionExpiredMessage", "Your session ended. Please sign in again.");
      navigate("/login", { replace: true });
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [navigate]);

  // A request that never reaches the server (dropped connection, proxy stall) used to leave
  // whichever page was open looking broken with no clue why, and a hard refresh alone often
  // didn't help since the underlying connection was still bad. Surface it instead, with a
  // one-click way to recover once the connection is back.
  const [connectionLost, setConnectionLost] = useState(false);
  useEffect(() => {
    const onIssue = () => setConnectionLost(true);
    const onOk = () => setConnectionLost(false);
    window.addEventListener(CONNECTION_ISSUE_EVENT, onIssue);
    window.addEventListener(CONNECTION_OK_EVENT, onOk);
    return () => {
      window.removeEventListener(CONNECTION_ISSUE_EVENT, onIssue);
      window.removeEventListener(CONNECTION_OK_EVENT, onOk);
    };
  }, []);

  const { features } = useFeatures();
  const { me, can } = useMe();
  // A campus role sees only the menus its switches allow (and groups that still have something in them).
  const navGroups = useMemo(
    () => visibleGroups(features)
      .map((g) => ({ ...g, items: g.items.filter((i) => can(permOf(i.to))) }))
      .filter((g) => g.items.length > 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [features, me],
  );
  const topItems = TOP_ITEMS.filter((i) => can(permOf(i.to)));

  // A custom role (e.g. Leave Section: reports + leave entry) that lands on a page it has no menu for - the
  // Dashboard right after sign-in, or an old bookmark - goes to its first allowed page instead.
  const firstAllowed = topItems[0]?.to ?? navGroups[0]?.items[0]?.to ?? null;
  useEffect(() => {
    if (me?.campus && !can(permOf(pathname)) && firstAllowed && firstAllowed !== pathname) {
      navigate(firstAllowed, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me, pathname, firstAllowed]);

  const activeGroup = GROUP_OF_PATH[pathname];
  // Accordion: only one group open at a time. Start with the group that holds
  // the current route open (if any).
  const [openGroup, setOpenGroup] = useState<string | null>(() => activeGroup ?? null);
  const toggle = (key: string) => setOpenGroup((cur) => (cur === key ? null : key));

  const groupHasActive = useMemo(() => activeGroup, [activeGroup]);

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-wrap">
          <div className="brand-icon-wrap">
            {org.OrgLogo ? (
              <img src={org.OrgLogo} alt={org.OrgName} style={{ width: 32, height: 32, objectFit: "contain", borderRadius: 6 }} />
            ) : (
              <svg className="brand-fingerprint" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 11c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z"/><path d="M12 11v7c0 2.21 1.79 4 4 4"/><path d="M12 18v-2"/><path d="M12 14v-1"/><path d="M12 11c-2.21 0-4 1.79-4 4v2"/><path d="M12 18v2"/></svg>
            )}
          </div>
          <div className="brand-text">
            <span className="brand-subtitle">{org.OrgSubtitle}</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {topItems.map((i) => (
            <NavItem key={i.to} to={i.to} icon={i.icon}>{i.label}</NavItem>
          ))}

          {navGroups.map((g) => {
            const isOpen = openGroup === g.key;
            return (
              <div className={`nav-group ${isOpen ? "open" : ""}`} key={g.key}>
                <button type="button" className="nav-group-header" onClick={() => toggle(g.key)} aria-expanded={isOpen}>
                  <span>{g.label}</span>
                  {groupHasActive === g.key && !isOpen && <span className="nav-group-dot" aria-hidden />}
                  {chevron}
                </button>
                <div className="nav-group-items">
                  {g.items.map((i) => (
                    <NavItem key={i.to} to={i.to} icon={i.icon}>{i.label}</NavItem>
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        <div className="sidebar-actions">
          <button type="button" onClick={logout} className="sidebar-logout">
            <span className="sidebar-nav-icon">{Icons.logout}</span>
            <span>Logout</span>
          </button>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div className="topbar-left">
            <PageTitle />
          </div>
          <div className="topbar-right">
            <div className="topbar-search">
              <span className="topbar-search-icon">{Icons.search}</span>
              <input type="search" placeholder="Search employees, devices..." aria-label="Search" />
            </div>
            <NotificationBell />
            <ProfileMenu onLogout={logout} />
          </div>
        </header>
        <main className="content">
          <div className="content-body">
            {connectionLost && (
              <div className="conn-lost-banner" role="alert">
                <span>Connection to the server was lost. Data on screen may be out of date.</span>
                <button type="button" onClick={() => window.location.reload()}>Reload</button>
              </div>
            )}
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
