import { useEffect, useState } from "react";

import { api } from "../../api/client";
import { Req } from "../../components/Req";

const DAYS = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const EMPTY = { ShiftName: "", StartTime: "09:00", EndTime: "16:00", GraceInMinutes: 10, HalfDayMinutes: 240, WeeklyOff: "Sunday", IsActive: "Y" };

export function StudentShiftsPage() {
  const [shifts, setShifts] = useState<any[]>([]);
  const [form, setForm] = useState<any>(EMPTY);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);

  const load = () => api.getStudentShifts().then(setShifts).catch((e) => setStatus({ text: e.message, ok: false }));
  useEffect(() => { load(); }, []);

  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));

  const save = async () => {
    const payload = { ...form, GraceInMinutes: Number(form.GraceInMinutes), HalfDayMinutes: Number(form.HalfDayMinutes) };
    try {
      if (editingId) await api.updateStudentShift(editingId, payload);
      else await api.createStudentShift(payload);
      setForm(EMPTY); setEditingId(null);
      setStatus({ text: "Shift saved.", ok: true });
      load();
    } catch (e: any) { setStatus({ text: e.message || "Save failed", ok: false }); }
  };

  const remove = async (id: number) => {
    if (!window.confirm("Delete this shift?")) return;
    try { await api.deleteStudentShift(id); load(); } catch (e: any) { setStatus({ text: e.message, ok: false }); }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Student Shifts</h2>
          <p className="sub">Class timings for students. Separate from employee shifts.</p>
        </div>
      </div>
      {status && <p className={status.ok ? "note-ok" : "note-err"}>{status.text}</p>}
      <div className="section-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>{editingId ? "Edit Shift" : "New Shift"}</h3>
        <div className="form-row-2">
          <label><span>Name <Req /></span><input value={form.ShiftName} onChange={(e) => set("ShiftName", e.target.value)} /></label>
          <label>Weekly off
            <select value={form.WeeklyOff || ""} onChange={(e) => set("WeeklyOff", e.target.value)}>
              {DAYS.map((d) => <option key={d} value={d}>{d || "None"}</option>)}
            </select>
          </label>
          <label><span>Start <Req /></span><input type="time" value={form.StartTime} onChange={(e) => set("StartTime", e.target.value)} /></label>
          <label><span>End <Req /></span><input type="time" value={form.EndTime} onChange={(e) => set("EndTime", e.target.value)} /></label>
          <label>Late grace (min)<input type="number" min={0} value={form.GraceInMinutes} onChange={(e) => set("GraceInMinutes", e.target.value)} /></label>
          <label>Half-day if worked under (min)<input type="number" min={0} value={form.HalfDayMinutes} onChange={(e) => set("HalfDayMinutes", e.target.value)} /></label>
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button className="btn btn-primary-purple" onClick={save} disabled={!form.ShiftName}>Save</button>
          {editingId && <button className="btn-device-ghost" onClick={() => { setEditingId(null); setForm(EMPTY); }}>Cancel</button>}
        </div>
      </div>
      <div className="section-card">
        <table className="table table-compact">
          <thead><tr><th>Name</th><th>Timing</th><th>Grace</th><th>Half-day &lt;</th><th>Weekly off</th><th /></tr></thead>
          <tbody>
            {shifts.map((s) => (
              <tr key={s.StudentShiftId}>
                <td><strong>{s.ShiftName}</strong></td>
                <td>{s.StartTime}–{s.EndTime}</td>
                <td>{s.GraceInMinutes} min</td>
                <td>{s.HalfDayMinutes} min</td>
                <td>{s.WeeklyOff || "—"}</td>
                <td>
                  <button className="btn-device-ghost" onClick={() => { setEditingId(s.StudentShiftId); setForm(s); }}>Edit</button>{" "}
                  <button className="btn-device-ghost" onClick={() => remove(s.StudentShiftId)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
