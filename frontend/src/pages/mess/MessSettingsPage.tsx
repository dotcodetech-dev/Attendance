import { useEffect, useState } from "react";

import { api } from "../../api/client";
import { FEATURES_CHANGED_EVENT } from "../../store/features";

const clockIcon = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="9" /><polyline points="12 7 12 12 15 14" />
  </svg>
);
const capIcon = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M22 10L12 5 2 10l10 5 10-5z" /><path d="M6 12v5c3 3 9 3 12 0v-5" />
  </svg>
);
const forkIcon = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2" /><path d="M7 2v20" /><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7" />
  </svg>
);

function StateBadge({ on }: { on: boolean }) {
  return <span className={"badge " + (on ? "badge-green" : "badge-gray")}>{on ? "Enabled" : "Off"}</span>;
}

export function MessSettingsPage() {
  const [enabled, setEnabled] = useState(false);
  const [meals, setMeals] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [messDeviceId, setMessDeviceId] = useState<string>("");
  const [autoPrint, setAutoPrint] = useState(false);
  const [studentModule, setStudentModule] = useState(false);
  const [studentLeaves, setStudentLeaves] = useState(true);
  const [absentWeeklyOff, setAbsentWeeklyOff] = useState(false);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => api.getMessSettings().then((s) => {
    setEnabled(s.enabled); setMeals(s.meals);
    setMessDeviceId(s.mess_device_id != null ? String(s.mess_device_id) : "");
    setAutoPrint(!!s.auto_print);
    setStudentModule(!!s.student_module_enabled);
    setStudentLeaves(s.student_leaves_enabled !== false);
    setAbsentWeeklyOff(!!s.student_absent_on_weekly_off);
  });
  useEffect(() => {
    load().catch(() => setStatus("Failed to load settings."));
    api.getDevices().then(setDevices).catch(() => setDevices([]));
  }, []);

  const setMeal = (i: number, key: string, val: string) =>
    setMeals(meals.map((m, j) => (j === i ? { ...m, [key]: val } : m)));

  const save = async () => {
    setSaving(true); setStatus("");
    try {
      await api.updateMessSettings({
        enabled,
        mess_device_id: messDeviceId ? Number(messDeviceId) : 0,
        auto_print: autoPrint,
        student_module_enabled: studentModule,
        student_leaves_enabled: studentLeaves,
        student_absent_on_weekly_off: absentWeeklyOff,
        meals: meals.map((m) => ({ MealType: m.MealType, StartTime: m.StartTime, EndTime: m.EndTime, IsActive: m.IsActive || "Y" })),
      });
      setStatus("Module configuration saved. Changes take effect immediately.");
      window.dispatchEvent(new Event(FEATURES_CHANGED_EVENT));
    } catch (e: any) {
      setStatus(e?.message || "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 900 }}>
      <div className="page-head">
        <div>
          <h2>Module Configuration</h2>
          <p className="sub">Switch optional modules on or off and set up mess tokens.</p>
        </div>
      </div>

      <div className="section-card">
        <p className="section-eyebrow">Provisions</p>
        <div className="provision-list">
          <div className="provision">
            <span className="provision-tile">{capIcon}</span>
            <div className="provision-body">
              <div className="provision-title">Student Attendance <StateBadge on={studentModule} /></div>
              <p className="provision-desc">
                Adds the Students menu (data, attendance, shifts, leaves, reports) and includes student faces in recognition.
                Turning it off hides the Students menu. Your student data is kept.
              </p>
            </div>
            <input type="checkbox" className="switch" checked={studentModule} onChange={(e) => setStudentModule(e.target.checked)}
              aria-label="Enable Student Attendance Module" />
          </div>
          <div className={"provision provision-sub" + (studentModule ? "" : " is-disabled")}>
            <div className="provision-body">
              <div className="provision-title">Student Leaves <StateBadge on={studentModule && studentLeaves} /></div>
              <p className="provision-desc">Leave types and leave requests for students. Turning it off hides the Student Leaves menu.</p>
            </div>
            <input type="checkbox" className="switch" checked={studentLeaves} disabled={!studentModule}
              onChange={(e) => setStudentLeaves(e.target.checked)} aria-label="Enable Student Leaves" />
          </div>
          <div className={"provision provision-sub" + (studentModule ? "" : " is-disabled")}>
            <div className="provision-body">
              <div className="provision-title">Absent on weekly off <StateBadge on={studentModule && absentWeeklyOff} /></div>
              <p className="provision-desc">
                A student with no punch is always marked Absent. Turn this on to also mark Absent on the weekly off day (Sunday by default)
                instead of "Weekly off". Approved leave still shows as Leave.
              </p>
            </div>
            <input type="checkbox" className="switch" checked={absentWeeklyOff} disabled={!studentModule}
              onChange={(e) => setAbsentWeeklyOff(e.target.checked)} aria-label="Mark absent on weekly off" />
          </div>
          <div className="provision">
            <span className="provision-tile">{forkIcon}</span>
            <div className="provision-body">
              <div className="provision-title">Mess Token Printing <StateBadge on={enabled} /></div>
              <p className="provision-desc">Issue one token per person per meal, within the meal windows below. Turning it off hides the Mess menu.</p>
            </div>
            <input type="checkbox" className="switch" checked={enabled} onChange={(e) => setEnabled(e.target.checked)}
              aria-label="Enable Mess Token Printing" />
          </div>
        </div>
      </div>

      <div className="section-card">
        <p className="section-eyebrow">Auto token on punch</p>
        <p style={{ margin: "0 0 16px", color: "var(--text-muted)", fontSize: 13.5, lineHeight: 1.5 }}>
          A punch on this device issues a token for the current meal. Open the{" "}
          <a href="/mess/kiosk" target="_blank" rel="noreferrer">Mess Kiosk</a> on the counter PC (connected to the thermal printer) to auto-print them.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 20, alignItems: "flex-end" }}>
          <div style={{ flex: "1 1 320px", minWidth: 0 }}>
            <label className="field-label" htmlFor="mess-device">Mess device</label>
            <select id="mess-device" style={{ width: "100%" }} value={messDeviceId} onChange={(e) => setMessDeviceId(e.target.value)}>
              <option value="">— None (manual only) —</option>
              {devices.map((d) => <option key={d.DeviceId} value={d.DeviceId}>{d.DeviceName} · {d.SerialNumber}</option>)}
            </select>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 12, height: 46, fontSize: 14.5 }}>
            <input type="checkbox" className="switch" checked={autoPrint} onChange={(e) => setAutoPrint(e.target.checked)} />
            Auto-print at kiosk
          </label>
        </div>
      </div>

      <div className="section-card">
        <p className="section-eyebrow">Meal timings</p>
        <div className="meal-list">
          {meals.map((m, i) => (
            <div className="meal-row" key={m.MealType}>
              <span className="meal-name">{m.MealType}</span>
              <div>
                <label className="field-label" htmlFor={`meal-${i}-start`}>Start</label>
                <div className="time-field">{clockIcon}
                  <input id={`meal-${i}-start`} type="time" value={m.StartTime} onChange={(e) => setMeal(i, "StartTime", e.target.value)} />
                </div>
              </div>
              <span className="meal-to">to</span>
              <div>
                <label className="field-label" htmlFor={`meal-${i}-end`}>End</label>
                <div className="time-field">{clockIcon}
                  <input id={`meal-${i}-end`} type="time" value={m.EndTime} onChange={(e) => setMeal(i, "EndTime", e.target.value)} />
                </div>
              </div>
              <label className="meal-active">
                Active
                <input type="checkbox" className="switch" checked={(m.IsActive || "Y") === "Y"}
                  onChange={(e) => setMeal(i, "IsActive", e.target.checked ? "Y" : "N")} aria-label={`${m.MealType} active`} />
              </label>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <button className="btn btn-primary-purple" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save configuration"}</button>
        {status && <span className={status.toLowerCase().includes("fail") ? "note-err" : "note-ok"} style={{ margin: 0, fontWeight: 600 }}>{status}</span>}
      </div>
    </div>
  );
}
