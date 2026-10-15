import { FormEvent, useEffect, useState } from "react";

import { api } from "../api/client";
import { Segmented, SectionHead, SwitchRow } from "../components/ConfigUi";
import { Icons } from "../components/SidebarIcons";
import { Req } from "../components/Req";

type Tone = "info" | "ok" | "err";
const toneOf = (msg: string): Tone => {
  if (/successfully/i.test(msg)) return "ok";
  if (/(disconnect|unable|fail|error|select a device)/i.test(msg)) return "err";
  return "info";
};

export function EnrollmentPage() {
  const [devices, setDevices] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [employeeRef, setEmployeeRef] = useState("");
  const [bioName, setBioName] = useState("FACE");
  const [bioData, setBioData] = useState("");
  const [allowUpdate, setAllowUpdate] = useState(false);
  const [status, setStatus] = useState("");
  const [checkingCompletion, setCheckingCompletion] = useState(false);
  const [pendingVerify, setPendingVerify] = useState(false);

  useEffect(() => {
    api.getDevices()
      .then((rows) => {
        setDevices(rows);
        if (rows.length > 0) setSelectedDeviceId(String(rows[0].DeviceId));
      })
      .catch(() => setDevices([]));
    api.getEmployees().then(setEmployees).catch(() => setEmployees([]));
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("");
    try {
      if (!selectedDeviceId) {
        setStatus("Please select a device.");
        return;
      }

      const enrollResult = await api.enrollOnDevice(Number(selectedDeviceId), {
        EmployeeRef: employeeRef.trim(),
        BioType: bioName,
        AllowUpdate: allowUpdate,
      });

      if (!enrollResult.enrollment_started) {
        setStatus(enrollResult.message || "Unable to start enrollment.");
        return;
      }

      setStatus(enrollResult.message || "Enrollment started. Complete capture on device...");
      setCheckingCompletion(true);
      setPendingVerify(false);

      const maxAttempts = 10;
      const delayMs = 2000;
      let completed = false;
      let interrupted = false;
      for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        // Strict check: treat complete only when biometric template is present on device.
        const result = await api.getEnrollStatus(Number(selectedDeviceId), employeeRef.trim(), bioName, allowUpdate, false);
        if (result.completed) {
          completed = true;
          break;
        }
        if (!result.connected) {
          setStatus(`Device disconnected while checking enrollment: ${result.message || "Unknown error"}`);
          interrupted = true;
          break;
        }
        setStatus(`Enrollment in progress... please complete capture on machine (${attempt}/${maxAttempts})`);
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }

      if (completed) {
        if (bioData.trim()) {
          await api.addBiometric(employeeRef.trim(), {
            BioName: bioName,
            Bio: bioData || null,
            BioDescription: "Uploaded from dashboard",
          });
        }
        setStatus("Enrollment completed successfully on device.");
      } else if (!interrupted) {
        setStatus("Enrollment command sent, but biometric capture is not confirmed yet. Check device popup and complete capture, then click Verify Completion.");
        setPendingVerify(true);
      }
    } catch (err) {
      setStatus((err as Error).message);
      setPendingVerify(false);
    } finally {
      setCheckingCompletion(false);
    }
  };

  const verifyNow = async () => {
    if (!selectedDeviceId || !employeeRef.trim()) return;
    setCheckingCompletion(true);
    try {
      const result = await api.getEnrollStatus(Number(selectedDeviceId), employeeRef.trim(), bioName, allowUpdate, false);
      if (result.completed) {
        setStatus("Enrollment completed successfully on device.");
        setPendingVerify(false);
      } else {
        setStatus(result.message || "Enrollment is still pending on device.");
      }
    } catch (err) {
      setStatus((err as Error).message);
    } finally {
      setCheckingCompletion(false);
    }
  };

  const tone = toneOf(status);

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Biometric Enrollment</h2>
          <p className="sub">Capture a face or fingerprint directly on a device. The person stands at the device while this page waits for the capture.</p>
        </div>
      </div>

      <form onSubmit={submit} className="section-card" style={{ maxWidth: 820 }}>
        <SectionHead icon={Icons.enrollment} title="Who and where" desc="Pick the device and the person to enroll" />
        <div className="emp-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <div className="field">
            <label htmlFor="en-dev">Device <Req /></label>
            <select id="en-dev" value={selectedDeviceId} onChange={(e) => setSelectedDeviceId(e.target.value)} required>
              {devices.length === 0 && <option value="">No devices</option>}
              {devices.map((device) => (
                <option key={device.DeviceId} value={device.DeviceId}>{device.DeviceName} ({device.DeviceIPAddress || "No IP"})</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="en-emp">Employee <Req /></label>
            <select id="en-emp" value={employeeRef} onChange={(e) => setEmployeeRef(e.target.value)} required>
              <option value="">Select employee…</option>
              {employees.map((e) => <option key={e.EmployeeId} value={e.EmployeeCode}>{e.EmployeeName} ({e.EmployeeCode})</option>)}
            </select>
          </div>
        </div>

        <div style={{ marginTop: 22 }}>
          <span className="field-label">What to capture</span>
          <Segmented label="Biometric type" value={bioName} onChange={setBioName} options={[["FACE", "Face"], ["FINGER", "Fingerprint"]]} />
        </div>

        <div className="switch-list">
          <SwitchRow id="en-upd" checked={allowUpdate} onChange={setAllowUpdate} title="Replace existing biometric"
            desc="Turn on to capture again for someone who is already enrolled." />
        </div>

        <details className="en-advanced">
          <summary>Advanced: attach a template</summary>
          <label className="field-label" htmlFor="en-tpl" style={{ marginTop: 12 }}>Biometric template payload</label>
          <textarea id="en-tpl" rows={5} style={{ width: "100%" }} value={bioData} onChange={(e) => setBioData(e.target.value)} placeholder="Optional. Saved with the employee after capture completes." />
        </details>

        <div style={{ marginTop: 22, display: "flex", gap: 12, flexWrap: "wrap" }}>
          <button type="submit" className="btn btn-primary-purple" disabled={checkingCompletion || !selectedDeviceId}>
            {checkingCompletion ? "Waiting for capture…" : "Start enrollment"}
          </button>
          {pendingVerify && (
            <button type="button" className="btn btn-outline-reports" onClick={verifyNow} disabled={checkingCompletion}>
              {checkingCompletion ? "Verifying…" : "Verify completion now"}
            </button>
          )}
        </div>

        {status && (
          <div className={"en-status is-" + tone} role="status" aria-live="polite">
            {tone === "info" && checkingCompletion && <span className="en-spinner" aria-hidden />}
            <span>{status}</span>
          </div>
        )}
      </form>
    </div>
  );
}
