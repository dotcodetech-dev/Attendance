import { useEffect, useState } from "react";

import { api } from "../api/client";
import { DirectionBadge } from "../components/DirectionBadge";
import { formatIST, formatDeviceIST } from "../utils/datetime";

export function LogsPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [comm, setComm] = useState<any[]>([]);

  const today = new Date();
  const firstOfMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;
  const todayStr = today.toISOString().slice(0, 10);
  const [recalcFrom, setRecalcFrom] = useState(firstOfMonth);
  const [recalcTo, setRecalcTo] = useState(todayStr);

  async function loadLogs() {
    try {
      setLoading(true);
      setError("");
      const data = await api.getLogs(500);
      setRows(data);
    } catch (err: any) {
      setRows([]);
      setError(err?.message || "Failed to load attendance logs.");
    } finally {
      setLoading(false);
    }
  }

  const loadComm = () => api.getDeviceCommLog(undefined, 60).then(setComm).catch(() => {});

  useEffect(() => {
    loadLogs();
    loadComm();
    api.getDevices().then((d) => {
      setDevices(d);
      if (d.length > 0) setDeviceId(String(d[0].DeviceId));
    }).catch(() => setDevices([]));
    const timer = window.setInterval(loadLogs, 20000);
    const commTimer = window.setInterval(loadComm, 4000); // live device activity
    return () => { window.clearInterval(timer); window.clearInterval(commTimer); };
  }, []);

  const fetchFromDevice = async () => {
    if (!deviceId) { setNote("Select a device first."); return; }
    setFetching(true);
    setNote("Fetching attendance from device over SDK… this can take up to a minute.");
    try {
      const res = await api.fetchDeviceAttendance(Number(deviceId));
      if (!res.connected) {
        setNote(res.message || "Could not connect to the device over the SDK (LAN / port 4370).");
      } else {
        setNote(`Fetched ${res.fetched} record(s); ${res.inserted} new stored.`);
        await loadLogs();
      }
    } catch (e: any) {
      setNote(e?.message || "Fetch failed.");
    } finally {
      setFetching(false);
    }
  };

  const recalculate = async () => {
    if (!recalcFrom || !recalcTo) { setNote("Select a date range for recalculation."); return; }
    setRecalculating(true);
    setNote("Recalculating attendance… this may take a moment for large date ranges.");
    try {
      const res = await api.recalculateAttendance({ from_date: recalcFrom, to_date: recalcTo });
      setNote(`Recalculated: ${res.employees} employee(s), ${res.days} day(s), ${res.rows_written} rows written.`);
    } catch (e: any) {
      setNote(e?.message || "Recalculation failed.");
    } finally {
      setRecalculating(false);
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Attendance Logs</h2>
          <p className="sub">Punches pushed by devices, plus manual SDK fetch for devices that aren't pushing.</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="field"><label>Fetch from device (SDK)</label>
          <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
            <option value="">Select device…</option>
            {devices.map((d) => (
              <option key={d.DeviceId} value={d.DeviceId}>{d.DeviceName} · {d.SerialNumber}</option>
            ))}
          </select>
        </div>
        <div className="toolbar-actions">
          <button className="btn btn-primary-purple" onClick={fetchFromDevice} disabled={fetching || !deviceId}>
            {fetching ? "Fetching…" : "Fetch from Device"}
          </button>
          <button className="btn btn-outline-reports" onClick={loadLogs} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      <div className="toolbar" style={{ marginTop: 8 }}>
        <div className="field"><label>From</label>
          <input type="date" value={recalcFrom} onChange={(e) => setRecalcFrom(e.target.value)} />
        </div>
        <div className="field"><label>To</label>
          <input type="date" value={recalcTo} onChange={(e) => setRecalcTo(e.target.value)} />
        </div>
        <div className="toolbar-actions">
          <button className="btn btn-primary-purple" onClick={recalculate} disabled={recalculating || !recalcFrom || !recalcTo}>
            {recalculating ? "Recalculating…" : "Recalculate Attendance"}
          </button>
        </div>
      </div>

      {note && <p className={note.toLowerCase().includes("fail") || note.toLowerCase().includes("could not") ? "note-err" : "note-ok"}>{note}</p>}
      {error && <p className="note-err">{error}</p>}

      <div className="section-card">
        <h3>Live Device Activity <span className="badge badge-blue">auto-refresh</span></h3>
        <p style={{ marginTop: 0, color: "var(--text-muted)", fontSize: 13 }}>
          What each device is sending. A <strong>PUSH ATTLOG</strong> line means the device auto-uploaded a punch —
          that's what you want. Only <em>ping</em>/<em>poll</em> means it's connected but not uploading attendance.
        </p>
        <div className="table-scroll" style={{ maxHeight: 220, overflowY: "auto" }}>
          <table className="table table-compact">
            <thead><tr><th>Time (IST)</th><th>Device SN</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>
              {comm.length === 0 ? (
                <tr><td colSpan={4} style={{ color: "var(--text-muted)" }}>No device activity captured yet. When a device contacts the server, it appears here.</td></tr>
              ) : comm.map((c, i) => (
                <tr key={i}>
                  <td>{formatIST(c.at)}</td>
                  <td>{c.sn}</td>
                  <td>
                    <span className={"badge " + (String(c.action).startsWith("PUSH") ? "badge-green" : c.action === "handshake" ? "badge-purple" : "badge-gray")}>{c.action}</span>
                  </td>
                  <td>{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="section-card">
        <div className="table-scroll">
          <table className="table table-compact">
            <thead>
              <tr>
                <th>ID</th><th>Device</th><th>Employee</th><th>Log Date</th>
                <th>Verification</th><th>Direction</th><th>Photo</th>
              </tr>
            </thead>
            <tbody>
              {!loading && rows.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ color: "var(--text-muted)", padding: "24px 12px" }}>
                    No attendance logs yet. If a device is online but not pushing, select it above and click
                    <strong> Fetch from Device</strong>.
                  </td>
                </tr>
              ) : null}
              {rows.map((row) => (
                <tr key={row.DeviceLogId}>
                  <td>{row.DeviceLogId}</td>
                  <td>{row.DeviceId}</td>
                  <td><strong>{row.EmployeeCode}</strong></td>
                  <td>{formatDeviceIST(row.LogDate)}</td>
                  <td>{row.VerificationType || "-"}</td>
                  <td><DirectionBadge value={row.Direction} /></td>
                  <td>{row.HasPhoto ? <span className="badge badge-green">Yes</span> : <span className="badge badge-gray">No</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
