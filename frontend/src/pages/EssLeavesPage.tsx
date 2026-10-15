import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import { EmployeeSearch, EmployeeSelect, useEmployees } from "../components/EmployeeSelect";
import { Flash, SectionHead, fmtDate } from "../components/ConfigUi";
import { Icons } from "../components/SidebarIcons";
import { Req } from "../components/Req";

type LeaveConfig = {
  LeaveConfigId: number;
  Code: string;
  Name: string;
  MaxPerYear?: number | null;
  IsPaid?: string | null;
  IsActive?: string | null;
};

type LeaveBalance = {
  LeaveConfigId: number;
  Code: string;
  Name: string;
  MaxPerYear: number;
  UsedDays: number;
  AvailableDays: number;
  IsPaid: string;
  IsActive: string;
  Unlimited?: boolean; // 0 days per year on the type = no yearly limit (OD, LOP ...)
};

/** Days that can still be taken, or Infinity for a type with no yearly limit. */
const left = (b: LeaveBalance) => (b.Unlimited ? Infinity : b.AvailableDays);

type LeaveRow = {
  LeaveRequestId: number;
  EmployeeCode: string;
  LeaveConfigId: number;
  FromDate: string;
  ToDate: string;
  Reason?: string | null;
  Status: string;
  AppliedAt: string;
};

const blankForm = { LeaveConfigId: 0, FromDate: "", ToDate: "", Reason: "" };

const dayCount = (from: string, to: string) => {
  if (!from || !to) return 0;
  const diff = Math.floor((new Date(to).getTime() - new Date(from).getTime()) / 86400000);
  return diff >= 0 ? diff + 1 : 0;
};

const statusBadge = (s: string) => {
  const v = s.toLowerCase();
  if (v === "approved") return "badge-green";
  if (v.startsWith("reject") || v.startsWith("cancel")) return "badge-red";
  if (v === "hodapproved") return "badge-blue";
  return "badge-amber";
};

const statusLabel = (s: string) =>
  s === "Pending" ? "Waiting for HOD / Manager" : s === "HodApproved" ? "Waiting for Principal / Director" : s;

/**
 * "apply": an employee's leave application (goes through HOD / Principal approval).
 * "admin": Leave Entry - an admin enters leave for anyone; it is saved as Approved at once and can be cancelled.
 */
export function EssLeavesPage({ mode = "apply" }: { mode?: "apply" | "admin" }) {
  const admin = mode === "admin";
  const employees = useEmployees();
  const [employeeCode, setEmployeeCode] = useState("");
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [leaveConfigs, setLeaveConfigs] = useState<LeaveConfig[]>([]);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [rows, setRows] = useState<LeaveRow[]>([]);
  const [form, setForm] = useState(blankForm);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);

  const selectedBalance = useMemo(
    () => balances.find((item) => item.LeaveConfigId === Number(form.LeaveConfigId)),
    [balances, form.LeaveConfigId]
  );
  const calendarDays = useMemo(() => dayCount(form.FromDate, form.ToDate), [form.FromDate, form.ToDate]);

  // The days a leave really deducts: weekly offs and holidays are skipped unless the leave type counts them.
  const [preview, setPreview] = useState<{ days: number; skipped_weekly_off: number; skipped_holidays: number } | null>(null);
  useEffect(() => {
    setPreview(null);
    if (!employeeCode || !form.LeaveConfigId || !form.FromDate || !form.ToDate || calendarDays <= 0) return;
    let live = true;
    api.previewLeaveDays({ employee_code: employeeCode, leave_config_id: Number(form.LeaveConfigId), from_date: form.FromDate, to_date: form.ToDate })
      .then((r: any) => { if (live) setPreview(r); })
      .catch(() => { /* fall back to the calendar count */ });
    return () => { live = false; };
  }, [employeeCode, form.LeaveConfigId, form.FromDate, form.ToDate, calendarDays]);
  const requestedDays = preview ? preview.days : calendarDays;

  const load = async (codeArg?: string) => {
    const code = (codeArg ?? employeeCode).trim();
    if (!code) {
      setRows([]); setBalances([]); setLoaded(false);
      return;
    }
    try {
      setLoading(true);
      setStatus(null);
      const [configsData, balancesData, rowsData] = await Promise.all([
        api.getLeaveConfigs(),
        api.getLeaveBalance(code, year),
        api.getMyLeaves({ employee_code: code }),
      ]);
      setLeaveConfigs(configsData);
      setBalances(balancesData);
      setRows(rowsData);
      setLoaded(true);
    } catch (err: any) {
      setRows([]);
      setBalances([]);
      setLoaded(false);
      setStatus({ text: err?.message || "Failed to load leave details.", ok: false });
    } finally {
      setLoading(false);
    }
  };

  const pickEmployee = (code: string) => {
    setEmployeeCode(code);
    setForm(blankForm);
    load(code); // loading straight away saves a click
  };

  const empName = employees.find((e) => String(e.EmployeeCode) === employeeCode)?.EmployeeName;

  const handleApply = async (event: FormEvent) => {
    event.preventDefault();
    setStatus(null);
    const code = employeeCode.trim();
    if (!code) { setStatus({ text: "Choose an employee first.", ok: false }); return; }
    if (!form.LeaveConfigId) { setStatus({ text: "Choose a leave type.", ok: false }); return; }
    if (!form.FromDate || !form.ToDate) { setStatus({ text: "Choose both the from and to dates.", ok: false }); return; }
    if (requestedDays <= 0) { setStatus({ text: "The to date is before the from date.", ok: false }); return; }
    if (selectedBalance && requestedDays > left(selectedBalance)) {
      setStatus({ text: `Not enough balance. ${selectedBalance.AvailableDays} day(s) available for ${selectedBalance.Code}.`, ok: false });
      return;
    }
    setApplying(true);
    try {
      const payload = {
        EmployeeCode: code,
        LeaveConfigId: Number(form.LeaveConfigId),
        FromDate: `${form.FromDate}T00:00:00`,
        ToDate: `${form.ToDate}T00:00:00`,
        Reason: form.Reason.trim() || null,
      };
      if (admin) {
        await api.adminLeaveEntry(payload);
        setStatus({ text: `${selectedBalance?.Code || "Leave"} saved and approved for ${empName || code}. Attendance for those days is updated.`, ok: true });
      } else {
        await api.applyLeave(payload);
        setStatus({ text: "Leave applied successfully.", ok: true });
      }
      setForm(blankForm);
      await load(code);
    } catch (err: any) {
      setStatus({ text: err?.message || (admin ? "Failed to save leave." : "Failed to apply leave."), ok: false });
    } finally {
      setApplying(false);
    }
  };

  const cancelLeave = async (row: LeaveRow, label: string) => {
    if (!window.confirm(`Cancel ${label} from ${fmtDate(row.FromDate)} to ${fmtDate(row.ToDate)}? The days go back to the balance and attendance is recalculated.`)) return;
    try {
      await api.cancelLeave(row.LeaveRequestId);
      setStatus({ text: `${label} cancelled.`, ok: true });
      await load(employeeCode);
    } catch (err: any) {
      setStatus({ text: err?.message || "Failed to cancel leave.", ok: false });
    }
  };

  const after = selectedBalance && !selectedBalance.Unlimited ? selectedBalance.AvailableDays - requestedDays : null;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{admin ? "Leave Entry" : "My Leaves"}</h2>
          <p className="sub">
            {admin
              ? "Enter leave for any employee: pick the person, the leave type and the dates. It is saved as approved straight away (no HOD / Principal step) and shows in attendance and reports."
              : "Check leave balances and apply for leave. A leave cannot be applied once its balance is used up."}
          </p>
        </div>
      </div>

      <div className="section-card ess-filter">
        <div className="hours-row" style={{ marginBottom: 0 }}>
          <div style={{ flex: "1 1 280px", minWidth: 0 }}>
            <label className="field-label" htmlFor="lv-emp">Employee <Req /></label>
            {admin
              ? <EmployeeSearch id="lv-emp" employees={employees} value={employeeCode} onChange={(c) => (c ? pickEmployee(c) : setEmployeeCode(""))} style={{ width: "100%" }} />
              : <EmployeeSelect id="lv-emp" employees={employees} value={employeeCode} onChange={pickEmployee} style={{ width: "100%" }} />}
          </div>
          <div>
            <label className="field-label" htmlFor="lv-year">Year</label>
            <input id="lv-year" type="number" value={year} onChange={(e) => setYear(Number(e.target.value || new Date().getFullYear()))} />
          </div>
          <button type="button" className="btn btn-outline-reports" onClick={() => load()} disabled={loading || !employeeCode}>{loading ? "Loading…" : "Reload"}</button>
        </div>
      </div>

      <Flash status={status} />

      {!loaded ? (
        <div className="section-card cfg-empty">
          <strong>Choose an employee</strong>
          <span>Their leave balances, an apply form and their past requests will appear here.</span>
        </div>
      ) : (
        <>
          <div className="lb-grid">
            {balances.map((item) => {
              const used = item.MaxPerYear ? Math.min(100, (item.UsedDays / item.MaxPerYear) * 100) : 0;
              const out = left(item) <= 0;
              return (
                <div key={item.LeaveConfigId} className={"lb-card" + (out ? " is-out" : "")}>
                  <div className="lb-top"><span className="lt-code lt-code-sm" style={{ margin: 0 }}>{item.Code}</span><span>{item.Name}</span></div>
                  {item.Unlimited
                    ? <div className="lb-num"><b>∞</b><span>no yearly limit</span></div>
                    : <div className="lb-num"><b>{item.AvailableDays}</b><span>of {item.MaxPerYear} left</span></div>}
                  <div className="lb-bar" aria-hidden><span style={{ width: `${used}%` }} /></div>
                  <div className="sd-sub">{item.UsedDays} used</div>
                </div>
              );
            })}
            {balances.length === 0 && <p style={{ margin: 0, color: "var(--text-muted)" }}>No leave types are set up yet.</p>}
          </div>

          <form onSubmit={handleApply} className="section-card">
            <SectionHead icon={Icons.leaves} title={admin ? "Enter leave (approved)" : "Apply for leave"} desc={empName ? `For ${empName}` : "Choose the type and dates"} />
            <div className="emp-grid">
              <div className="field">
                <label htmlFor="lv-type">Leave type <Req /></label>
                <select id="lv-type" value={form.LeaveConfigId} onChange={(e) => setForm({ ...form, LeaveConfigId: Number(e.target.value) })}>
                  <option value={0}>Select leave type…</option>
                  {balances.map((item) => (
                    <option key={item.LeaveConfigId} value={item.LeaveConfigId} disabled={left(item) <= 0}>
                      {item.Code} · {item.Name} ({item.Unlimited ? "no limit" : `${item.AvailableDays} left`})
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="lv-from">From <Req /></label>
                <input id="lv-from" type="date" value={form.FromDate} onChange={(e) => setForm({ ...form, FromDate: e.target.value, ToDate: form.ToDate && form.ToDate < e.target.value ? e.target.value : form.ToDate })} />
              </div>
              <div className="field">
                <label htmlFor="lv-to">To <Req /></label>
                <input id="lv-to" type="date" min={form.FromDate} value={form.ToDate} onChange={(e) => setForm({ ...form, ToDate: e.target.value })} />
              </div>
              <div className="field field-full">
                <label htmlFor="lv-reason">Reason</label>
                <input id="lv-reason" value={form.Reason} placeholder="Optional" onChange={(e) => setForm({ ...form, Reason: e.target.value })} />
              </div>
            </div>

            {selectedBalance && (
              <div className={"lv-summary" + (after !== null && after < 0 ? " is-bad" : "")}>
                <strong>{requestedDays} day{requestedDays === 1 ? "" : "s"} requested</strong>
                {preview && preview.skipped_weekly_off + preview.skipped_holidays > 0 && (
                  <span>
                    {[preview.skipped_weekly_off ? `${preview.skipped_weekly_off} weekly off` : "", preview.skipped_holidays ? `${preview.skipped_holidays} holiday` : ""].filter(Boolean).join(" and ")} not counted
                  </span>
                )}
                {selectedBalance.Unlimited ? (
                  <span>{selectedBalance.Code} has no yearly limit</span>
                ) : (
                  <span>
                    {selectedBalance.Code} balance {selectedBalance.AvailableDays} → {after !== null ? Math.max(after, 0) : 0}
                    {after !== null && after < 0 ? ` (short by ${-after})` : ""}
                  </span>
                )}
              </div>
            )}

            <div style={{ marginTop: 18 }}>
              <button type="submit" className="btn btn-primary-purple" disabled={applying || (!!selectedBalance && left(selectedBalance) <= 0)}>
                {admin ? (applying ? "Saving…" : "Save leave") : (applying ? "Applying…" : "Apply leave")}
              </button>
            </div>
          </form>

          <div className="section-card cfg-table-card">
            <div className="cfg-toolbar"><strong>{admin ? "Leaves of this employee" : "Leave requests"}</strong><span className="cfg-count">{rows.length}</span></div>
            {rows.length === 0 ? (
              <div className="cfg-empty"><strong>No leave requests yet</strong><span>{admin ? "Leaves you enter will be listed here." : "Requests you apply for will be listed here with their status."}</span></div>
            ) : (
              <table className="table cfg-table">
                <thead><tr><th>Type</th><th>From</th><th>To</th><th>Days</th><th>Status</th><th>Reason</th>{admin && <th />}</tr></thead>
                <tbody>
                  {rows.map((row) => {
                    const config = leaveConfigs.find((item) => item.LeaveConfigId === row.LeaveConfigId);
                    return (
                      <tr key={row.LeaveRequestId}>
                        <td>{config ? <><span className="lt-code lt-code-sm">{config.Code}</span>{config.Name}</> : row.LeaveConfigId}</td>
                        <td>{fmtDate(row.FromDate)}</td>
                        <td>{fmtDate(row.ToDate)}</td>
                        <td>{dayCount(row.FromDate.slice(0, 10), row.ToDate.slice(0, 10))}</td>
                        <td><span className={"badge " + statusBadge(row.Status)}>{statusLabel(row.Status)}</span></td>
                        <td>{row.Reason || "—"}</td>
                        {admin && (
                          <td>
                            {!["Rejected", "Cancelled"].includes(row.Status) && (
                              <button type="button" className="btn-outline-gray" onClick={() => cancelLeave(row, config?.Code || "Leave")}>Cancel</button>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
