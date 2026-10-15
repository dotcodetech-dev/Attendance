import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import { Flash, SectionHead } from "../components/ConfigUi";
import { Icons } from "../components/SidebarIcons";
import { Req } from "../components/Req";
import { ReaderDiagnostics } from "../components/ReaderDiagnostics";

const COMMANDS: { value: string; label: string; help: string; risky?: boolean }[] = [
  { value: "ClearLogs", label: "Clear logs", help: "Erase the attendance logs stored on the device.", risky: true },
  { value: "EnrollFace", label: "Enroll face", help: "Start face enrollment on the device." },
  { value: "EnrollFingerprint", label: "Enroll fingerprint", help: "Start fingerprint enrollment on the device." },
  { value: "ResetTransactionStamp", label: "Reset transaction stamp", help: "Make the device resend its attendance logs from the start.", risky: true },
  { value: "ResetOperationStamp", label: "Reset operation stamp", help: "Make the device resend its user data from the start.", risky: true },
  { value: "UnlockDoor", label: "Unlock door", help: "Open the door connected to the device.", risky: true },
  { value: "Reboot", label: "Reboot", help: "Restart the device. It is offline for about a minute.", risky: true },
];

const statusBadge = (s?: string) => {
  const v = (s || "").toLowerCase();
  if (/(done|success|complete|executed|ok)/.test(v)) return "badge-green";
  if (/(fail|error|reject)/.test(v)) return "badge-red";
  if (/(pending|queued|wait|sent)/.test(v)) return "badge-amber";
  return "badge-gray";
};

export function CommandsPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [command, setCommand] = useState("ClearLogs");
  const [payload, setPayload] = useState("");
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [sending, setSending] = useState(false);

  const load = () => api.getCommands().then(setRows).catch(() => setRows([]));
  useEffect(() => {
    load();
    api.getDevices().then((d: any[]) => { setDevices(d); if (d.length) setDeviceId(String(d[0].DeviceId)); }).catch(() => setDevices([]));
  }, []);

  const deviceName = useMemo(() => new Map(devices.map((d) => [d.DeviceId, d.DeviceName])), [devices]);
  const selected = COMMANDS.find((c) => c.value === command);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!deviceId) { setStatus({ text: "Choose a device.", ok: false }); return; }
    const dev = deviceName.get(Number(deviceId)) || `device ${deviceId}`;
    if (selected?.risky && !window.confirm(`${selected.label} on ${dev}?\n\n${selected.help}`)) return;
    setSending(true);
    setStatus(null);
    try {
      await api.createCommand({ DeviceId: Number(deviceId), command, payload });
      setStatus({ text: `${selected?.label} queued for ${dev}. It runs the next time the device checks in.`, ok: true });
      setPayload("");
      await load();
    } catch (err: any) {
      setStatus({ text: err?.message || "Could not send the command.", ok: false });
    } finally {
      setSending(false);
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Device Commands</h2>
          <p className="sub">Queue an action for a device. Devices pick up commands the next time they check in.</p>
        </div>
      </div>

      <form onSubmit={submit} className="section-card">
        <SectionHead icon={Icons.commands} title="Send a command" desc="Choose a device and what it should do" />
        <div className="emp-grid">
          <div className="field">
            <label htmlFor="cm-dev">Device <Req /></label>
            <select id="cm-dev" value={deviceId} onChange={(e) => setDeviceId(e.target.value)} required>
              {devices.length === 0 && <option value="">No devices</option>}
              {devices.map((d) => <option key={d.DeviceId} value={d.DeviceId}>{d.DeviceName}{d.DeviceIPAddress ? ` (${d.DeviceIPAddress})` : ""}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="cm-cmd">Command <Req /></label>
            <select id="cm-cmd" value={command} onChange={(e) => setCommand(e.target.value)}>
              {COMMANDS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="cm-pay">Payload</label>
            <input id="cm-pay" value={payload} onChange={(e) => setPayload(e.target.value)} placeholder="Optional" />
          </div>
        </div>
        {selected && (
          <div className={"cmd-note" + (selected.risky ? " is-risky" : "")}>
            <strong>{selected.label}.</strong> {selected.help}{selected.risky ? " You will be asked to confirm." : ""}
          </div>
        )}
        <div style={{ marginTop: 18, display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
          <button type="submit" className="btn btn-primary-purple" disabled={sending || !deviceId}>{sending ? "Sending…" : "Send command"}</button>
          <Flash status={status} />
        </div>
      </form>

      <div className="section-card cfg-table-card">
        <div className="cfg-toolbar">
          <strong>Command history</strong>
          <button type="button" className="btn btn-outline-reports" style={{ height: 36 }} onClick={load}>Refresh</button>
        </div>
        {rows.length === 0 ? (
          <div className="cfg-empty"><strong>No commands yet</strong><span>Commands you send will be listed here with their status.</span></div>
        ) : (
          <table className="table cfg-table">
            <thead><tr><th>#</th><th>Device</th><th>Title</th><th>Command</th><th>Status</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.DeviceCommandId}>
                  <td>{row.DeviceCommandId}</td>
                  <td>{deviceName.get(row.DeviceId) || `Device ${row.DeviceId}`}</td>
                  <td>{row.Title}</td>
                  <td><code className="cmd-code" title={String(row.DeviceCommand).length > 120 ? "Long biometric payload shortened" : undefined}>
                    {String(row.DeviceCommand).length > 120 ? `${String(row.DeviceCommand).slice(0, 80)}… (${String(row.DeviceCommand).length} chars)` : row.DeviceCommand}
                  </code></td>
                  <td><span className={"badge " + statusBadge(row.Status)}>{row.Status || "—"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ReaderDiagnostics devices={devices} />
    </div>
  );
}
