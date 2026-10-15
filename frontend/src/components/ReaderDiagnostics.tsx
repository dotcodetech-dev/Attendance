import { useEffect, useState } from "react";

import { api } from "../api/client";
import { Flash, SectionHead } from "./ConfigUi";
import { Icons } from "./SidebarIcons";

type Row = { id: number; at: string; direction: string; kind: string; query: string; body: string; length: number };

const clock = (iso: string) => new Date(iso).toLocaleTimeString("en-GB");

/** What a push reader has sent to the server and what we sent back: handshake, commands, replies, uploaded tables. */
export function ReaderDiagnostics({ devices }: { devices: any[] }) {
  const [deviceId, setDeviceId] = useState("");
  const [pin, setPin] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    if (!deviceId && devices.length) setDeviceId(String(devices[0].DeviceId));
  }, [devices, deviceId]);

  const load = async () => {
    if (!deviceId) return;
    try { setRows(await api.getAdmsLog(Number(deviceId), 200)); }
    catch (e: any) { setStatus({ text: e?.message || "Could not load the reader log.", ok: false }); }
  };
  useEffect(() => { setRows([]); load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [deviceId]);

  const run = async () => {
    setBusy(true); setStatus(null);
    try {
      const r = await api.runReaderDiagnostics(Number(deviceId), pin.trim() || undefined);
      setStatus({ text: r.message, ok: true });
    } catch (e: any) {
      setStatus({ text: e?.message || "Could not queue the diagnostics.", ok: false });
    } finally { setBusy(false); }
  };

  const copy = async () => {
    const text = rows.slice().reverse().map((r) =>
      `[${r.at}] ${r.direction === "in" ? "READER->SERVER" : "SERVER->READER"} ${r.kind}${r.query ? " ?" + r.query : ""}${r.body ? "\n" + r.body : ""}`).join("\n\n");
    try { await navigator.clipboard.writeText(text); setStatus({ text: `Copied ${rows.length} log entries.`, ok: true }); }
    catch { setStatus({ text: "Could not copy. Select the text in the table instead.", ok: false }); }
  };

  return (
    <div className="section-card" style={{ marginTop: 18 }}>
      <SectionHead icon={Icons.devices} title="Reader diagnostics" desc="See exactly what a push reader sends and receives, to find out why faces or fingerprints do not transfer" />
      <div className="emp-grid">
        <div className="field">
          <label htmlFor="rd-dev">Reader</label>
          <select id="rd-dev" value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
            {devices.length === 0 && <option value="">No devices</option>}
            {devices.map((d) => <option key={d.DeviceId} value={d.DeviceId}>{d.DeviceName}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="rd-pin">User ID to test (optional)</label>
          <input id="rd-pin" value={pin} onChange={(e) => setPin(e.target.value)} placeholder="e.g. 10" />
          <span className="field-hint">Someone who has a face or fingerprint on that reader. Leave blank to ask only for the reader's details and user list.</span>
        </div>
      </div>
      <div style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <button type="button" className="btn btn-primary-purple" onClick={run} disabled={busy || !deviceId}>{busy ? "Queuing…" : "Run diagnostics"}</button>
        <button type="button" className="btn btn-outline-reports" onClick={load} disabled={!deviceId}>Refresh log</button>
        <button type="button" className="btn btn-outline-reports" onClick={copy} disabled={rows.length === 0}>Copy log</button>
        <Flash status={status} />
      </div>
      <p className="field-hint" style={{ marginTop: 10 }}>
        After "Run diagnostics", wait up to a minute and press Refresh log. Templates and photos are shortened here; nothing biometric is kept in full.
      </p>

      {rows.length === 0 ? (
        <div className="cfg-empty"><strong>No reader traffic recorded yet</strong><span>Entries appear as the reader checks in, uploads data and answers commands.</span></div>
      ) : (
        <table className="table cfg-table" style={{ marginTop: 10 }}>
          <thead><tr><th>Time</th><th>Direction</th><th>What</th><th>Details</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td style={{ whiteSpace: "nowrap" }}>{clock(r.at)}</td>
                <td><span className={"badge " + (r.direction === "in" ? "badge-green" : "badge-amber")}>{r.direction === "in" ? "From reader" : "To reader"}</span></td>
                <td><code className="cmd-code">{r.kind}</code></td>
                <td>
                  {r.query && <div className="adms-query">{r.query}</div>}
                  {r.body && (
                    <details>
                      <summary>{r.body.split("\n")[0].slice(0, 90)}{r.length > 90 ? ` … (${r.length} chars)` : ""}</summary>
                      <pre className="adms-body">{r.body}</pre>
                    </details>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
