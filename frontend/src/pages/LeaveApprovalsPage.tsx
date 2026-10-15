import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { ConfigModal, Flash, SectionHead, Segmented, fmtDate } from "../components/ConfigUi";
import { EmployeeSelect, useEmployees } from "../components/EmployeeSelect";
import { Icons } from "../components/SidebarIcons";

type Tab = "waiting" | "open" | "decided" | "all";

const KIND_LABEL: Record<string, string> = {
  admin: "Admin. You can act at any step.",
  hod: "HOD / Manager. You decide the first step for your department.",
  principal: "Principal / Director. You decide the second and final step.",
  other: "Your login is not set up as an approver, so you can view requests but not decide them.",
};

const STATUS_BADGE: Record<string, [string, string]> = {
  Pending: ["badge-amber", "Waiting for HOD / Manager"],
  HodApproved: ["badge-blue", "Waiting for Principal / Director"],
  Approved: ["badge-green", "Approved"],
  Rejected: ["badge-red", "Rejected"],
};

type StepState = "done" | "current" | "skipped" | "rejected" | "todo";

/** The two steps as a small tracker, worked out from the request's status and trail. */
function stepStates(item: any): [StepState, StepState] {
  const trail: any[] = item.Trail || [];
  const at = (level: number, action: string) => trail.some((t) => t.level === level && t.action === action);
  const one: StepState = at(1, "Approved") ? "done" : at(1, "Skipped") ? "skipped" : at(1, "Rejected") ? "rejected" : item.Status === "Pending" ? "current" : "todo";
  const two: StepState = item.Status === "Approved" ? "done" : at(2, "Rejected") ? "rejected" : item.Status === "HodApproved" ? "current" : "todo";
  return [one, two];
}

const STEP_ICON: Record<StepState, string> = { done: "✓", current: "●", skipped: "–", rejected: "✕", todo: "" };

function Steps({ item }: { item: any }) {
  const [a, b] = stepStates(item);
  const step = (label: string, s: StepState) => (
    <li className={"la-step is-" + s}>
      <span className="la-dot" aria-hidden>{STEP_ICON[s]}</span>
      <span>{label}<em>{s === "skipped" ? "skipped" : s === "current" ? "waiting" : s === "done" ? "approved" : s === "rejected" ? "rejected" : ""}</em></span>
    </li>
  );
  return (
    <ol className="la-steps" aria-label="Approval steps">
      {step("HOD / Manager", a)}
      <li className="la-line" aria-hidden />
      {step("Principal / Director", b)}
    </ol>
  );
}

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "");

export function LeaveApprovalsPage() {
  const employees = useEmployees();
  const [me, setMe] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("waiting");
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);

  // Decision popup
  const [deciding, setDeciding] = useState<{ item: any; action: "Approved" | "Rejected" } | null>(null);
  const [remarks, setRemarks] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  // Approver setup
  const [overview, setOverview] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [setup, setSetup] = useState({ login: "", employee: "", role: "Manager" });
  const [setupStatus, setSetupStatus] = useState<{ text: string; ok: boolean } | null>(null);

  const loadMe = () => api.getApprovalMe().then(setMe).catch(() => setMe(null));
  const loadOverview = () => api.getApprovers().then(setOverview).catch(() => setOverview(null));
  const load = useCallback(() => {
    setLoading(true);
    api.getLeaveApprovals(tab)
      .then(setItems)
      .catch((e) => { setItems([]); setStatus({ text: e?.message || "Could not load requests.", ok: false }); })
      .finally(() => setLoading(false));
  }, [tab]);

  useEffect(() => { loadMe(); loadOverview(); api.getUsers().then(setUsers).catch(() => setUsers([])); }, []);
  useEffect(() => { load(); }, [load]);

  const open = (item: any, action: "Approved" | "Rejected") => { setDeciding({ item, action }); setRemarks(""); setFormError(""); };
  const close = () => { setDeciding(null); setFormError(""); };

  const submitDecision = async (e: FormEvent) => {
    e.preventDefault();
    if (!deciding) return;
    if (deciding.action === "Rejected" && !remarks.trim()) { setFormError("Give a reason so the employee knows why."); return; }
    setSaving(true);
    try {
      await api.decideLeaveRequest(deciding.item.LeaveRequestId, deciding.action, remarks.trim());
      setStatus({ text: deciding.action === "Approved" ? "Approved." : "Rejected.", ok: true });
      close();
      load(); loadMe();
    } catch (err: any) {
      setFormError(err?.message || "Could not save the decision.");
    } finally {
      setSaving(false);
    }
  };

  const saveApprover = async () => {
    if (!setup.login) { setSetupStatus({ text: "Choose a login.", ok: false }); return; }
    if (!setup.employee) { setSetupStatus({ text: "Choose the employee this login belongs to.", ok: false }); return; }
    try {
      await api.linkUser({ login_name: setup.login, employee_code: setup.employee, role_name: setup.role });
      setSetupStatus({ text: `${setup.login} is now a ${setup.role === "Manager" ? "HOD / Manager" : "Principal / Director"} approver.`, ok: true });
      loadOverview(); loadMe(); load();
    } catch (err: any) {
      setSetupStatus({ text: err?.message || "Could not save.", ok: false });
    }
  };

  const nobody = me && me.kind === "other";
  const noHod = overview?.departments_without_hod ?? [];

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Leave Approvals</h2>
          <p className="sub">Every leave request goes to the HOD / Manager of the employee's department first, then to the Principal / Director. Only fully approved leave counts in attendance.</p>
        </div>
        <Link to="/ess/my-leaves" className="btn btn-outline-reports">Apply for leave</Link>
      </div>

      {me && (
        <div className={"la-me" + (nobody ? " is-warn" : "")}>
          <span className="cfg-avatar" aria-hidden>{(me.login || "?").charAt(0).toUpperCase()}</span>
          <div>
            <strong>{me.login}{me.employee_name ? ` · ${me.employee_name}` : ""}{me.department ? ` · ${me.department}` : ""}</strong>
            <span>{KIND_LABEL[me.kind]}</span>
          </div>
        </div>
      )}

      <Flash status={status} />

      <div className="la-tabs">
        <Segmented label="Requests" value={tab} onChange={(v) => setTab(v as Tab)}
          options={[["waiting", `Waiting for me${me ? ` (${me.waiting})` : ""}`], ["open", "All open"], ["decided", "Decided"], ["all", "Everything"]]} />
        <button type="button" className="btn btn-outline-reports" style={{ height: 40 }} onClick={() => { load(); loadMe(); }} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
      </div>

      {items.length === 0 && !loading ? (
        <div className="section-card cfg-empty">
          <strong>{tab === "waiting" ? "Nothing is waiting for you" : "No requests here"}</strong>
          <span>{tab === "waiting" ? "New leave requests that need your decision will appear here and in the bell." : "Try another tab."}</span>
        </div>
      ) : (
        <div className="la-list">
          {items.map((it) => {
            const [badge, label] = STATUS_BADGE[it.Status] ?? ["badge-gray", it.Status];
            return (
              <article key={it.LeaveRequestId} className="la-card">
                <header className="la-head">
                  <div className="cfg-person">
                    <span className="cfg-avatar" aria-hidden>{(it.EmployeeName || it.EmployeeCode).trim().charAt(0).toUpperCase()}</span>
                    <div><strong>{it.EmployeeName || it.EmployeeCode}</strong><div className="sd-sub">{it.EmployeeCode}{it.Department ? ` · ${it.Department}` : ""}</div></div>
                  </div>
                  <span className={"badge " + badge}>{label}</span>
                </header>

                <div className="la-body">
                  <div className="la-when">
                    <span className="lt-code lt-code-sm" style={{ margin: 0 }}>{it.LeaveCode}</span>
                    <strong>{fmtDate(it.FromDate)}{it.FromDate !== it.ToDate ? ` → ${fmtDate(it.ToDate)}` : ""}</strong>
                    <span className="la-days">{it.Days} day{it.Days === 1 ? "" : "s"}</span>
                  </div>
                  {it.Reason && <p className="la-reason">“{it.Reason}”</p>}
                  <Steps item={it} />
                  {it.Trail.length > 0 && (
                    <ul className="la-trail">
                      {it.Trail.map((t: any, i: number) => (
                        <li key={i}>
                          <b className={t.action === "Rejected" ? "is-no" : t.action === "Skipped" ? "is-skip" : "is-yes"}>{t.action === "Skipped" ? "Skipped" : t.action}</b>
                          <span>{t.role}{t.by && t.by !== "system" ? ` (${t.by})` : ""}{t.at ? ` · ${when(t.at)}` : ""}{t.remarks ? ` — ${t.remarks}` : ""}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <footer className="la-actions">
                  {it.CanAct ? (
                    <>
                      <button type="button" className="btn btn-primary-purple" onClick={() => open(it, "Approved")}>Approve</button>
                      <button type="button" className="btn btn-outline-reports shift-delete" onClick={() => open(it, "Rejected")}>Reject</button>
                    </>
                  ) : (
                    it.CantActReason && <span className="sd-sub">{it.CantActReason}</span>
                  )}
                </footer>
              </article>
            );
          })}
        </div>
      )}

      {/* Approver setup */}
      <section className="section-card" style={{ marginTop: 28 }}>
        <SectionHead icon={Icons.roles} title="Approvers" desc="Who can approve leave, and which departments still need a HOD / Manager" />
        {noHod.length > 0 && (
          <div className="la-nohod">
            <strong>No HOD / Manager yet:</strong>
            {noHod.map((d: string) => <span key={d} className="badge badge-amber">{d}</span>)}
            <span className="sd-sub">Leave from these departments skips the first step and goes straight to the Principal / Director.</span>
          </div>
        )}
        <div className="la-approvers">
          {[...(overview?.hods ?? []), ...(overview?.principals ?? [])].map((a: any) => (
            <div key={a.LoginName} className="la-approver">
              <span className={"badge " + (/principal|director/i.test(a.Role || "") ? "badge-purple" : "badge-blue")}>{/principal|director/i.test(a.Role || "") ? "Principal / Director" : "HOD / Manager"}</span>
              <strong>{a.EmployeeName || a.LoginName}</strong>
              <span className="sd-sub">{a.LoginName}{a.Department ? ` · ${a.Department}` : ""}{!a.EmployeeCode ? " · not linked to an employee" : ""}</span>
            </div>
          ))}
          {!(overview?.hods?.length || overview?.principals?.length) && <p style={{ margin: 0, color: "var(--text-muted)" }}>No approvers are set up yet.</p>}
        </div>

        <div className="switch-list">
          <p className="section-eyebrow" style={{ margin: "0 0 4px" }}>Set up an approver</p>
          <p className="sd-sub" style={{ margin: "0 0 12px" }}>
            Create a portal login for the person in <Link to="/employees" className="notif-link">Employees</Link> (choose the role Manager or Principal), or link an existing login here.
          </p>
          <div className="hours-row" style={{ marginBottom: 0 }}>
            <div style={{ flex: "1 1 200px", minWidth: 0 }}>
              <label className="field-label" htmlFor="ap-login">Login</label>
              <select id="ap-login" style={{ width: "100%" }} value={setup.login} onChange={(e) => setSetup({ ...setup, login: e.target.value })}>
                <option value="">Select login…</option>
                {users.map((u) => <option key={u.UserId} value={u.LoginName}>{u.LoginName} ({u.RoleName || "no role"})</option>)}
              </select>
            </div>
            <div style={{ flex: "1 1 260px", minWidth: 0 }}>
              <label className="field-label" htmlFor="ap-emp">Employee</label>
              <EmployeeSelect id="ap-emp" employees={employees} value={setup.employee} onChange={(v) => setSetup({ ...setup, employee: v })} style={{ width: "100%" }} />
            </div>
            <div>
              <label className="field-label" htmlFor="ap-role">Role</label>
              <select id="ap-role" value={setup.role} onChange={(e) => setSetup({ ...setup, role: e.target.value })}>
                <option value="Manager">HOD / Manager</option>
                <option value="Principal">Principal / Director</option>
              </select>
            </div>
            <button type="button" className="btn btn-outline-reports" onClick={saveApprover}>Save approver</button>
          </div>
          <Flash status={setupStatus} />
        </div>
      </section>

      {deciding && (
        <ConfigModal
          title={deciding.action === "Approved" ? "Approve leave" : "Reject leave"}
          subtitle={`${deciding.item.EmployeeName || deciding.item.EmployeeCode} · ${deciding.item.LeaveCode} · ${deciding.item.Days} day(s)`}
          icon={Icons.leaves}
          onClose={close} onSubmit={submitDecision} error={formError} saving={saving}
          submitLabel={deciding.action === "Approved" ? (deciding.item.Status === "Pending" ? "Approve and send to Principal" : "Approve") : "Reject leave"}
        >
          <section className="emp-section">
            <div className="field field-full">
              <label htmlFor="dc-note">{deciding.action === "Approved" ? "Note (optional)" : "Reason (required)"}</label>
              <textarea id="dc-note" rows={3} style={{ width: "100%" }} value={remarks} onChange={(e) => setRemarks(e.target.value)}
                placeholder={deciding.action === "Approved" ? "Anything the next approver or the employee should know" : "Why is this leave not approved?"} />
              {deciding.action === "Approved" && deciding.item.Status === "Pending" && (
                <span className="field-hint">After you approve, it goes to the Principal / Director for the final decision.</span>
              )}
            </div>
          </section>
        </ConfigModal>
      )}
    </div>
  );
}
