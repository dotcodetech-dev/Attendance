import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import { ConfigModal, Flash, SectionHead } from "../components/ConfigUi";
import { Icons } from "../components/SidebarIcons";
import { Req } from "../components/Req";

type Login = {
  UserId: number;
  LoginName: string;
  RoleName: string;
  CustomRole: boolean;
  Institution: string | null;
  EmployeeCode: string | null;
  EmployeeName: string | null;
  StringCode: string | null;
  Department: string | null;
  Blocked: boolean;
  CanSignIn: boolean;
  BlockReason: string | null;
};

const ROLE_BADGE: Record<string, string> = { admin: "badge-red", manager: "badge-blue", hod: "badge-blue", principal: "badge-amber", director: "badge-amber" };

/** Admin only: every login of every role, with a password reset and block / unblock. Passwords are stored hashed,
 *  so they cannot be shown; the Admin sets a new one and shares it. */
export function UsersLoginsPage() {
  const [rows, setRows] = useState<Login[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [resetFor, setResetFor] = useState<Login | null>(null);
  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    api.getLogins()
      .then((data: Login[]) => setRows(Array.isArray(data) ? data : []))
      .catch((e: any) => { setRows([]); setStatus({ text: e?.message || "Could not load logins.", ok: false }); })
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const roles = useMemo(() => {
    const counts = new Map<string, number>();
    rows.forEach((r) => counts.set(r.RoleName, (counts.get(r.RoleName) || 0) + 1));
    return Array.from(counts.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [rows]);

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => (!roleFilter || r.RoleName === roleFilter)
      && (!q || [r.LoginName, r.EmployeeName, r.EmployeeCode, r.StringCode, r.Department, r.Institution]
        .some((v) => v && String(v).toLowerCase().includes(q))));
  }, [rows, search, roleFilter]);

  const openReset = (r: Login) => { setResetFor(r); setPwd(""); setConfirm(""); setShowPwd(false); setFormError(""); };
  const closeReset = () => setResetFor(null);

  const saveReset = async (e: FormEvent) => {
    e.preventDefault();
    if (!resetFor) return;
    if (pwd.length < 4) { setFormError("Password must be at least 4 characters."); return; }
    if (pwd !== confirm) { setFormError("The two passwords do not match."); return; }
    setSaving(true); setFormError("");
    try {
      await api.resetPassword({ login_name: resetFor.LoginName, new_password: pwd });
      setStatus({ text: `Password for "${resetFor.LoginName}" changed. Share the new password with them.`, ok: true });
      setResetFor(null);
    } catch (err: any) {
      setFormError(err?.message || "Could not change the password.");
    } finally { setSaving(false); }
  };

  const toggleBlock = async (r: Login) => {
    const block = !r.Blocked;
    if (block && !window.confirm(`Block "${r.LoginName}"? They are signed out and cannot sign in until unblocked.`)) return;
    try {
      await api.blockLogin({ login_name: r.LoginName, blocked: block });
      setStatus({ text: `"${r.LoginName}" ${block ? "blocked" : "unblocked"}.`, ok: true });
      load();
    } catch (err: any) {
      setStatus({ text: err?.message || "Could not change the login.", ok: false });
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Users &amp; Logins</h2>
          <p className="sub">Every login of every role: Admin, Manager, Employee and the roles added on User Roles. Reset a password or block a login here.</p>
        </div>
      </div>

      <div className="section-card ess-filter">
        <div className="hours-row" style={{ marginBottom: 0 }}>
          <div style={{ flex: "1 1 320px", minWidth: 0 }}>
            <label className="field-label" htmlFor="ul-search">Search</label>
            <input id="ul-search" type="search" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Login name, employee name, Employee Code, department…" style={{ width: "100%" }} />
          </div>
          <div>
            <label className="field-label" htmlFor="ul-role">Role</label>
            <select id="ul-role" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
              <option value="">All roles ({rows.length})</option>
              {roles.map(([name, n]) => <option key={name} value={name}>{name} ({n})</option>)}
            </select>
          </div>
        </div>
      </div>

      <Flash status={status} />

      <div className="section-card cfg-table-card">
        <div className="cfg-toolbar"><strong>Logins</strong><span className="cfg-count">{shown.length} of {rows.length}</span></div>
        {loading ? (
          <div className="cfg-empty"><span>Loading…</span></div>
        ) : shown.length === 0 ? (
          <div className="cfg-empty"><strong>No login matches</strong><span>Clear the search or pick another role.</span></div>
        ) : (
          <div className="ul-table-wrap">
            <table className="table cfg-table">
              <thead><tr><th>Login</th><th>Role</th><th>Employee</th><th>Status</th><th /></tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={`${r.UserId}-${r.LoginName}`}>
                    <td><strong>{r.LoginName}</strong></td>
                    <td>
                      <span className={"badge " + (r.CustomRole ? "badge-purple" : ROLE_BADGE[r.RoleName.toLowerCase()] || "badge-gray")}>{r.RoleName}</span>
                      {r.Institution && <div className="ul-sub">{r.Institution}</div>}
                    </td>
                    <td>
                      {r.EmployeeName || r.EmployeeCode ? <>
                        <div>{r.EmployeeName || "(not found)"}</div>
                        <div className="ul-sub">{[r.StringCode || r.EmployeeCode, r.Department].filter(Boolean).join(" · ")}</div>
                      </> : <span className="ul-sub">Not linked</span>}
                    </td>
                    <td>
                      {r.Blocked ? <span className="badge badge-red">Blocked</span>
                        : r.CanSignIn ? <span className="badge badge-green">Active</span>
                        : <span className="badge badge-amber" title={r.BlockReason || ""}>Access ended</span>}
                    </td>
                    <td className="cfg-actions">
                      <button type="button" className="btn btn-outline-reports" onClick={() => openReset(r)}>Reset password</button>
                      {r.UserId > 0 && (
                        <button type="button" className={"btn btn-outline-reports" + (r.Blocked ? "" : " shift-delete")} onClick={() => toggleBlock(r)}>
                          {r.Blocked ? "Unblock" : "Block"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {resetFor && (
        <ConfigModal title="Reset password" subtitle={`Login "${resetFor.LoginName}" · ${resetFor.RoleName}`} icon={Icons.user}
          onClose={closeReset} onSubmit={saveReset} error={formError} saving={saving} submitLabel="Change password">
          <section className="emp-section">
            <SectionHead icon={Icons.user} title="New password" desc="The old password stops working at once" />
            <div className="emp-grid">
              <div className="field">
                <label htmlFor="ul-pwd">New password <Req /></label>
                <input id="ul-pwd" type={showPwd ? "text" : "password"} autoComplete="new-password" value={pwd} onChange={(e) => setPwd(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="ul-confirm">Confirm password <Req /></label>
                <input id="ul-confirm" type={showPwd ? "text" : "password"} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              </div>
            </div>
            <label className="ul-show"><input type="checkbox" checked={showPwd} onChange={(e) => setShowPwd(e.target.checked)} /> Show passwords</label>
          </section>
        </ConfigModal>
      )}
    </div>
  );
}
