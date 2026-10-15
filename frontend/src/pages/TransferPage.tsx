import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { SwitchRow } from "../components/ConfigUi";
import { LoadingNote, SkeletonRows } from "../components/LoadingNote";
import { ProgressBar } from "../components/ProgressBar";
import { TemplateCells, templateTotals } from "../components/TemplateCells";

interface TransferJob {
  job_id: number;
  status: string;
  phase: string | null;
  total_users: number;
  batch_size: number;
  total_batches: number;
  include_face: boolean;
  include_finger: boolean;
  include_card: boolean;
  include_photo: boolean;
  sequential_biometrics: boolean;
  face_queued: number;
  face_executed: number;
  face_failed: number;
  finger_queued: number;
  finger_executed: number;
  finger_failed: number;
  total_commands: number;
  pending_commands: number;
  sent_commands: number;
  executed_commands: number;
  failed_commands: number;
  created_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  face_skipped?: number;
  finger_skipped?: number;
  skipped_note?: string | null;
}

const STATUS_LABEL: Record<string, string> = {
  running_face:   "Transferring Face Data...",
  running_finger: "Transferring Finger Data...",
  running_card:   "Transferring Card Data...",
  running_photo:  "Transferring Photo Data...",
  completed:      "Transfer Complete",
  failed:         "Transfer Failed",
};

const DATA_TYPES: { key: "face" | "finger" | "card" | "photo"; label: string; help: string }[] = [
  { key: "face", label: "Face", help: "Face templates" },
  { key: "finger", label: "Finger", help: "Fingerprint templates" },
  { key: "card", label: "Card", help: "RFID card numbers" },
  { key: "photo", label: "Photo", help: "Profile photos" },
];

export function TransferPage() {
  const [devices, setDevices] = useState<any[]>([]);
  const [sourceDeviceId, setSourceDeviceId] = useState("");
  const [sourceUsers, setSourceUsers] = useState<any[]>([]);
  const [userSearch, setUserSearch] = useState("");
  const [selectedUserCodes, setSelectedUserCodes] = useState<string[]>([]);
  const [selectedTargetIds, setSelectedTargetIds] = useState<number[]>([]);
  const [includeFace, setIncludeFace] = useState(true);
  const [includeFinger, setIncludeFinger] = useState(true);
  const [includeCard, setIncludeCard] = useState(true);
  const [includePhoto, setIncludePhoto] = useState(false);
  const [sequentialBiometrics, setSequentialBiometrics] = useState(true);
  const [batchSize, setBatchSize] = useState(500);
  const [status, setStatus] = useState("");
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sdkPushing, setSdkPushing] = useState(false);
  const [activeJob, setActiveJob] = useState<TransferJob | null>(null);
  const [autoSync, setAutoSync] = useState<boolean | null>(null);
  const [autoSyncSaving, setAutoSyncSaving] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.getAutoSync().then((r: any) => setAutoSync(!!r.enabled)).catch(() => setAutoSync(null));
  }, []);

  const toggleAutoSync = async (on: boolean) => {
    setAutoSyncSaving(true);
    try {
      await api.setAutoSync(on);
      setAutoSync(on);
    } catch (err) {
      setStatus(`Could not save auto-sync: ${(err as Error).message}`);
    } finally {
      setAutoSyncSaving(false);
    }
  };

  // Load devices on mount
  useEffect(() => {
    api.getDevices()
      .then((rows) => {
        setDevices(rows);
        if (rows.length > 0) setSourceDeviceId(String(rows[0].DeviceId));
      })
      .catch(() => setDevices([]));
  }, []);

  // Poll active job every 5 seconds
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (!activeJob || activeJob.status === "completed" || activeJob.status === "failed") return;

    pollRef.current = setInterval(async () => {
      try {
        const updated: TransferJob = await api.getTransferJob(activeJob.job_id);
        setActiveJob(updated);
      } catch {
        // Silently ignore poll errors - device may be temporarily unreachable
      }
    }, 5000);

    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeJob?.job_id, activeJob?.status]);

  const targetDeviceOptions = useMemo(
    () => devices.filter((d) => String(d.DeviceId) !== sourceDeviceId),
    [devices, sourceDeviceId],
  );

  const filteredUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    if (!q) return sourceUsers;
    return sourceUsers.filter((u) => String(u.EmployeeCode).toLowerCase().includes(q) || String(u.EmployeeName || "").toLowerCase().includes(q));
  }, [sourceUsers, userSearch]);

  const loadSourceUsers = async () => {
    if (!sourceDeviceId) { setStatus("Please select source device."); return; }
    setLoadingUsers(true);
    setStatus("");
    try {
      const users = await api.getDeviceMachineUsers(Number(sourceDeviceId));
      setSourceUsers(users);
      setSelectedUserCodes([]);
      setUserSearch("");
      if (users.length === 0) setStatus("No users found in source device.");
      else if (users[0].Source === "push") setStatus(`${users.length} user(s) from the reader's last push to this server (remote reader). Templates transfer from the server copy; the target reader receives them on its next poll.`);
    } catch (err) {
      setSourceUsers([]);
      setStatus(`Unable to read users: ${(err as Error).message}`);
    } finally {
      setLoadingUsers(false);
    }
  };

  const toggleUser   = (code: string) =>
    setSelectedUserCodes((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );

  const toggleTarget = (deviceId: number) =>
    setSelectedTargetIds((prev) =>
      prev.includes(deviceId) ? prev.filter((id) => id !== deviceId) : [...prev, deviceId],
    );

  const anyType = includeFace || includeFinger || includeCard || includePhoto;

  // Transfer only sends templates this server already holds (what the readers pushed or the SDK
  // read). A selected user with nothing stored is skipped - the target reader is never asked to
  // enrol them on its own screen - so say so before the transfer starts.
  const selectedUsers = useMemo(
    () => sourceUsers.filter((u) => selectedUserCodes.includes(u.EmployeeCode)),
    [sourceUsers, selectedUserCodes],
  );
  const missingFace = includeFace ? selectedUsers.filter((u) => !(u.FaceCount > 0) && !u.HasFacePhoto) : [];
  const missingFinger = includeFinger ? selectedUsers.filter((u) => !(u.FingerCount > 0)) : [];
  const nothingToSend =
    selectedUsers.length > 0 && anyType &&
    (!includeFace || missingFace.length === selectedUsers.length) &&
    (!includeFinger || missingFinger.length === selectedUsers.length) &&
    !includeCard && !includePhoto;
  const nameList = (users: any[]) =>
    users.slice(0, 6).map((u) => u.EmployeeName || u.EmployeeCode).join(", ") + (users.length > 6 ? ` and ${users.length - 6} more` : "");

  // What still blocks the Start button, in plain words.
  const blockers: string[] = [];
  if (!sourceDeviceId) blockers.push("Choose a source device");
  if (selectedUserCodes.length === 0) blockers.push("Select at least one user");
  if (!anyType) blockers.push("Choose what to transfer");
  if (selectedTargetIds.length === 0) blockers.push("Select a target device");
  if (nothingToSend) blockers.push("None of the selected users has a stored template to send - read them from the source reader first");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!sourceDeviceId) { setStatus("Please select source device."); return; }
    if (selectedUserCodes.length === 0) { setStatus("Please select at least one user."); return; }
    if (selectedTargetIds.length === 0) { setStatus("Please select at least one target device."); return; }
    if (!anyType) {
      setStatus("Select at least one data type: Face, Finger, Card, or Photo.");
      return;
    }
    setSubmitting(true);
    setStatus("");
    setActiveJob(null);
    try {
      const response = await api.transferBiometric({
        source_device_id:        Number(sourceDeviceId),
        employee_codes:          selectedUserCodes,
        target_device_ids:       selectedTargetIds,
        include_face:            includeFace,
        include_finger:          includeFinger,
        include_card:            includeCard,
        include_photo:           includePhoto,
        sequential_biometrics:   sequentialBiometrics,
        batch_size:              batchSize,
      });
      // Immediately fetch full job details and start polling
      const job: TransferJob = await api.getTransferJob(response.job_id);
      setActiveJob(job);
    } catch (err) {
      setStatus((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const retryJob = async () => {
    if (!activeJob) return;
    try {
      await api.retryTransferJob(activeJob.job_id);
      const updated: TransferJob = await api.getTransferJob(activeJob.job_id);
      setActiveJob(updated);
    } catch (err) {
      setStatus((err as Error).message);
    }
  };

  const pushViaSdk = async () => {
    if (!activeJob || sdkPushing) return;
    setSdkPushing(true);
    setStatus("");
    try {
      const updated: TransferJob = await api.executeTransferJobSdk(activeJob.job_id);
      setActiveJob(updated);
      if (updated.status === "completed") {
        setStatus("Transfer completed via direct SDK push.");
      } else if (updated.error_message) {
        setStatus(updated.error_message);
      } else {
        setStatus("");
      }
    } catch (err) {
      setStatus(`SDK push failed: ${(err as Error).message}`);
    } finally {
      setSdkPushing(false);
    }
  };

  const isRunning = activeJob && activeJob.status !== "completed" && activeJob.status !== "failed";
  const typeState: Record<string, [boolean, (v: boolean) => void]> = {
    face: [includeFace, setIncludeFace], finger: [includeFinger, setIncludeFinger],
    card: [includeCard, setIncludeCard], photo: [includePhoto, setIncludePhoto],
  };
  const chosenTypes = DATA_TYPES.filter((t) => typeState[t.key][0]).map((t) => t.label);
  const allFilteredSelected = filteredUsers.length > 0 && filteredUsers.every((u) => selectedUserCodes.includes(u.EmployeeCode));
  const sourceName = devices.find((d) => String(d.DeviceId) === sourceDeviceId)?.DeviceName;
  const statusTone = /(unable|error|failed)/i.test(status) ? "err" : "info";

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Transfer Biometric Data</h2>
          <p className="sub">Copy users and their face, fingerprint and card data from one device to others. Work through the steps, then start.</p>
        </div>
      </div>

      {/* ── Active Job Progress Panel ── */}
      {activeJob && (
        <div className={"tf-job is-" + (activeJob.status === "completed" ? "ok" : activeJob.status === "failed" ? "err" : "run")}>
          <div className="tf-job-head">
            <div>
              <div className="tf-job-title">
                Job #{activeJob.job_id}
                {isRunning && <span className="tf-live"><i /> Live</span>}
              </div>
              <div className="tf-job-status">{STATUS_LABEL[activeJob.status] || activeJob.status}</div>
              <div className="tf-job-meta">
                {activeJob.total_users} users · {activeJob.total_batches} batch{activeJob.total_batches !== 1 ? "es" : ""} of {activeJob.batch_size}
                {activeJob.sequential_biometrics ? " · Sequential mode" : ""}
              </div>
            </div>
            <div className="tf-job-actions">
              {(isRunning || activeJob.status === "failed") && (
                <button type="button" className="btn btn-outline-reports" onClick={pushViaSdk} disabled={sdkPushing}>
                  {sdkPushing ? "Pushing via SDK…" : "Push via SDK now"}
                </button>
              )}
              {activeJob.status === "failed" && (
                <button type="button" className="btn btn-primary-purple" onClick={retryJob} disabled={sdkPushing}>Retry failed commands</button>
              )}
            </div>
          </div>

          {activeJob.status === "failed" && activeJob.error_message && <div className="tf-job-error">{activeJob.error_message}</div>}
          {activeJob.skipped_note && (
            <p className="tf-note" role="status" style={{ color: "#b45309" }}>
              <strong>Skipped:</strong> {activeJob.skipped_note}
            </p>
          )}

          {activeJob.total_commands > 0 && (
            <div className="tf-prog">
              <div className="tf-prog-head">
                <span><strong>Overall</strong></span>
                <span>
                  {activeJob.executed_commands} / {activeJob.total_commands} done
                  {activeJob.failed_commands > 0 && <b className="tf-fail"> · {activeJob.failed_commands} failed</b>}
                </span>
              </div>
              <ProgressBar value={activeJob.executed_commands} total={activeJob.total_commands} color={activeJob.failed_commands > 0 ? "#dc4c5b" : "#1aa45b"} />
              <p className="tf-prog-caption">
                Waiting {activeJob.pending_commands} · With the reader {activeJob.sent_commands} · Done {activeJob.executed_commands} · Failed {activeJob.failed_commands}
              </p>
            </div>
          )}

          {sdkPushing && (
            <div className="tf-wait">
              <LoadingNote
                message="Sending to the reader over SDK…"
                hint="This can take a few minutes. Keep this page open; the counts above update as it goes."
                bar
              />
            </div>
          )}
          {isRunning && !sdkPushing && activeJob.sent_commands + activeJob.executed_commands === 0 && (
            <div className="tf-wait">
              <LoadingNote
                message="Waiting for the reader to pick up the commands…"
                hint="Readers collect commands on their next check-in, usually within 10–60 seconds. This page updates by itself. If the reader is on your network you can use Push via SDK now."
                bar
              />
            </div>
          )}

          {activeJob.include_face && (
            <div className="tf-prog">
              <div className="tf-prog-head">
                <span>
                  <strong>Face data</strong>
                  {activeJob.status === "running_face" && <em className="is-active"> · in progress</em>}
                  {activeJob.sequential_biometrics && activeJob.include_finger && activeJob.status !== "running_face" && activeJob.status !== "completed" && activeJob.face_queued === 0 && (
                    <em> · waiting</em>
                  )}
                </span>
                <span>
                  {activeJob.face_executed} / {activeJob.face_queued} done
                  {activeJob.face_failed > 0 && <b className="tf-fail"> · {activeJob.face_failed} failed</b>}
                </span>
              </div>
              <ProgressBar value={activeJob.face_executed} total={activeJob.face_queued} color={activeJob.face_failed > 0 ? "#dc4c5b" : "#1aa45b"} />
            </div>
          )}

          {activeJob.include_finger && (
            <div className="tf-prog">
              <div className="tf-prog-head">
                <span>
                  <strong>Finger data</strong>
                  {activeJob.status === "running_finger" && <em className="is-active"> · in progress</em>}
                  {activeJob.sequential_biometrics && activeJob.status === "running_face" && <em> · waiting for face to finish</em>}
                </span>
                <span>
                  {activeJob.finger_executed} / {activeJob.finger_queued} done
                  {activeJob.finger_failed > 0 && <b className="tf-fail"> · {activeJob.finger_failed} failed</b>}
                </span>
              </div>
              <ProgressBar value={activeJob.finger_executed} total={activeJob.finger_queued} color={activeJob.finger_failed > 0 ? "#dc4c5b" : "#5a35e0"} />
            </div>
          )}

          <div className="tf-tiles">
            <div><b>{activeJob.pending_commands}</b><span>Pending</span></div>
            <div><b>{activeJob.sent_commands}</b><span>Sent to device</span></div>
            <div className="is-good"><b>{activeJob.executed_commands}</b><span>Executed</span></div>
            <div className={activeJob.failed_commands > 0 ? "is-bad" : ""}><b>{activeJob.failed_commands}</b><span>Failed</span></div>
          </div>

          {activeJob.sent_commands > 0 && isRunning && (
            <p className="tf-note">
              {activeJob.sent_commands} command(s) sent to the device and waiting for it to confirm.
              They reset automatically if the device does not respond within 10 minutes.
            </p>
          )}
          {activeJob.status === "completed" && <p className="tf-done">All biometric data transferred successfully.</p>}
        </div>
      )}

      {autoSync !== null && (
        <section className="section-card" style={{ marginBottom: 16 }}>
          <div className="switch-list">
            <SwitchRow id="tf-autosync" checked={autoSync} onChange={toggleAutoSync}
              title={autoSyncSaving ? "Keep readers in sync automatically (saving…)" : "Keep readers in sync automatically"}
              desc={autoSync
                ? "On: when a reader sends this server a new face, fingerprint or face photo for a person, the same data is queued for every other reader that already has that person (how eBioServer keeps its readers in step). Nothing is sent to readers the person is not on."
                : "Off: data a reader sends here stays on the server until you run a transfer. Turn on to push new enrolments to the person's other readers automatically."} />
          </div>
        </section>
      )}

      <form onSubmit={submit} className="tf-layout">
        <div className="tf-steps">
          {/* 1. Source */}
          <section className="section-card tf-step">
            <header><span className="tf-num">1</span><div><h3>Source device</h3><p>Where the users and their data are copied from</p></div></header>
            <div className="hours-row" style={{ marginBottom: 0 }}>
              <div style={{ flex: "1 1 280px", minWidth: 0 }}>
                <label className="field-label" htmlFor="tf-src">Device</label>
                <select id="tf-src" style={{ width: "100%" }} value={sourceDeviceId} onChange={(e) => { setSourceDeviceId(e.target.value); setSourceUsers([]); setSelectedUserCodes([]); setSelectedTargetIds((t) => t.filter((id) => String(id) !== e.target.value)); }}>
                  {devices.length === 0 && <option value="">No devices</option>}
                  {devices.map((d) => <option key={d.DeviceId} value={d.DeviceId}>{d.DeviceName} ({d.DeviceIPAddress || "No IP"})</option>)}
                </select>
              </div>
              <button type="button" className="btn btn-outline-reports" onClick={loadSourceUsers} disabled={loadingUsers || !sourceDeviceId}>
                {loadingUsers ? "Reading users…" : sourceUsers.length ? "Reload users" : "Load users"}
              </button>
            </div>
            {loadingUsers && (
              <div className="tf-wait">
                <LoadingNote
                  message={<>Reading users from {sourceName || "the source device"}…</>}
                  hint="A reader on your network can take up to 30 seconds. A remote reader answers straight away from the last copy it sent to this server."
                  bar
                />
              </div>
            )}
          </section>

          {/* 2. Users */}
          <section className="section-card tf-step">
            <header><span className="tf-num">2</span><div><h3>Choose users</h3><p>{sourceUsers.length ? `${sourceUsers.length} users on ${sourceName || "the device"}` : "Load users from the source device first"}</p></div></header>
            {sourceUsers.length === 0 ? (
              loadingUsers
                ? <SkeletonRows count={4} />
                : <div className="cfg-empty" style={{ padding: "26px 12px" }}><span>No users loaded yet. Select Load users in step 1.</span></div>
            ) : (
              <>
                <div className="tf-users-bar">
                  <input type="search" placeholder="Search by code or name" value={userSearch} onChange={(e) => setUserSearch(e.target.value)} aria-label="Search users" />
                  <button type="button" className="btn btn-outline-reports" onClick={() => setSelectedUserCodes(Array.from(new Set([...selectedUserCodes, ...filteredUsers.map((u) => u.EmployeeCode)])))}>
                    Select {userSearch ? "shown" : "all"} ({filteredUsers.length})
                  </button>
                  <button type="button" className="btn btn-outline-reports" onClick={() => setSelectedUserCodes([])} disabled={selectedUserCodes.length === 0}>Clear</button>
                </div>
                {(() => {
                  const t = templateTotals(sourceUsers);
                  return (
                    <p className="tf-tpl-summary">
                      {t.users} {t.users === 1 ? "user" : "users"} · {t.withFace} with a face · {t.withFinger} with a fingerprint · {t.withPhoto} with a photo
                      <em> (what this reader has sent to the server)</em>
                    </p>
                  );
                })()}
                <div className="tf-users">
                  <table className="table cfg-table">
                    <thead>
                      <tr>
                        <th style={{ width: 44 }}>
                          <input type="checkbox" aria-label="Select all shown" checked={allFilteredSelected}
                            onChange={(e) => e.target.checked
                              ? setSelectedUserCodes(Array.from(new Set([...selectedUserCodes, ...filteredUsers.map((u) => u.EmployeeCode)])))
                              : setSelectedUserCodes(selectedUserCodes.filter((c) => !filteredUsers.some((u) => u.EmployeeCode === c)))} />
                        </th>
                        <th>Code</th><th>Name</th><th>Role</th><th>Enabled</th><th>Face</th><th>Fingers</th><th>Photo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredUsers.map((user) => {
                        const on = selectedUserCodes.includes(user.EmployeeCode);
                        return (
                          <tr key={user.EmployeeCode} className={on ? "is-picked" : ""} onClick={() => toggleUser(user.EmployeeCode)} style={{ cursor: "pointer" }}>
                            <td><input type="checkbox" checked={on} onChange={() => toggleUser(user.EmployeeCode)} onClick={(e) => e.stopPropagation()} aria-label={`Select ${user.EmployeeName || user.EmployeeCode}`} /></td>
                            <td>{user.EmployeeCode}</td>
                            <td>{user.EmployeeName || "—"}</td>
                            <td>{user.Role || "—"}</td>
                            <td>{user.Enabled === true ? <span className="badge badge-green">Yes</span> : user.Enabled === false ? <span className="badge badge-gray">No</span> : "—"}</td>
                            <TemplateCells user={user} />
                          </tr>
                        );
                      })}
                      {filteredUsers.length === 0 && <tr><td colSpan={8} style={{ color: "var(--text-muted)" }}>No users match the search.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>

          {/* 3. What to transfer */}
          <section className="section-card tf-step">
            <header><span className="tf-num">3</span><div><h3>What to transfer</h3><p>Pick the data types to copy</p></div></header>
            <div className="tf-types" role="group" aria-label="Data types">
              {DATA_TYPES.map((t) => {
                const [on, set] = typeState[t.key];
                return (
                  <button key={t.key} type="button" className={"tf-type" + (on ? " on" : "")} aria-pressed={on} onClick={() => set(!on)}>
                    <span className="tf-type-check" aria-hidden>{on ? "✓" : ""}</span>
                    <strong>{t.label}</strong><span>{t.help}</span>
                  </button>
                );
              })}
            </div>
            {(missingFace.length > 0 || missingFinger.length > 0) && (
              <p className="tf-note" role="status" style={{ color: "#b45309", marginTop: 12 }}>
                {missingFace.length > 0 && (
                  <>
                    <strong>{missingFace.length} of {selectedUsers.length} selected user(s) have no face on this server</strong>
                    {" "}({nameList(missingFace)}).{" "}
                  </>
                )}
                {missingFinger.length > 0 && (
                  <>
                    <strong>{missingFinger.length} have no fingerprint on this server</strong>
                    {" "}({nameList(missingFinger)}).{" "}
                  </>
                )}
                Transfer only copies what this server already holds (a face template, or the photo an AI-face reader enrolled from),
                so these are skipped - the target reader is never asked to enrol them on its screen. To include them, read the data from
                {" "}{sourceName || "the source reader"} first (Devices &gt; Users &gt; Refresh from reader), or enrol them on that reader so it
                pushes the data here.{includePhoto ? " Photo is on, so an AI-face reader will try to build the face from the profile photo instead." : " Turning on Photo lets an AI-face reader build the face from the profile photo."}
              </p>
            )}
            {includeFace && includeFinger && (
              <div className="switch-list">
                <SwitchRow id="tf-seq" checked={sequentialBiometrics} onChange={setSequentialBiometrics}
                  title="Sequential mode (recommended)"
                  desc={sequentialBiometrics ? "Transfers all face data first, then fingerprints. Easier on the device." : "Face and fingerprint commands are queued together, which can overload slower devices."} />
              </div>
            )}
            <div style={{ marginTop: 18 }}>
              <label className="field-label" htmlFor="tf-batch">Batch size</label>
              <select id="tf-batch" value={batchSize} onChange={(e) => setBatchSize(Number(e.target.value))}>
                <option value={100}>100 users</option>
                <option value={250}>250 users</option>
                <option value={500}>500 users (default)</option>
                <option value={1000}>1000 users</option>
              </select>
              <span className="field-hint" style={{ display: "block", marginTop: 6 }}>How many users are sent to a device at a time.</span>
            </div>
          </section>

          {/* 4. Targets */}
          <section className="section-card tf-step">
            <header><span className="tf-num">4</span><div><h3>Target devices</h3><p>Where the data is copied to</p></div></header>
            {targetDeviceOptions.length === 0 ? (
              <div className="cfg-empty" style={{ padding: "22px 12px" }}><span>There is no other device to copy to. Add another device first.</span></div>
            ) : (
              <div className="tf-devices">
                {targetDeviceOptions.map((d) => {
                  const on = selectedTargetIds.includes(d.DeviceId);
                  return (
                    <label key={d.DeviceId} className={"tf-device" + (on ? " on" : "")}>
                      <input type="checkbox" checked={on} onChange={() => toggleTarget(d.DeviceId)} />
                      <span><strong>{d.DeviceName}</strong><small>{d.DeviceIPAddress || "No IP"} · #{d.DeviceId}</small></span>
                    </label>
                  );
                })}
              </div>
            )}
          </section>
        </div>

        {/* Summary */}
        <aside className="tf-summary" aria-label="Transfer summary">
          <p className="section-eyebrow">Summary</p>
          <dl>
            <div><dt>From</dt><dd>{sourceName || "—"}</dd></div>
            <div><dt>Users</dt><dd>{selectedUserCodes.length}</dd></div>
            <div><dt>Data</dt><dd>{chosenTypes.length ? chosenTypes.join(", ") : "—"}</dd></div>
            <div><dt>To</dt><dd>{selectedTargetIds.length ? `${selectedTargetIds.length} device${selectedTargetIds.length === 1 ? "" : "s"}` : "—"}</dd></div>
          </dl>
          {blockers.length > 0 && !isRunning && (
            <ul className="tf-todo">{blockers.map((b) => <li key={b}>{b}</li>)}</ul>
          )}
          <button type="submit" className="btn btn-primary-purple" style={{ width: "100%" }} disabled={submitting || !!isRunning || blockers.length > 0}>
            {submitting ? "Starting transfer…" : isRunning ? "Transfer running…" : "Start transfer"}
          </button>
          {submitting && (
            <div className="tf-wait">
              <LoadingNote message="Creating the transfer and queuing commands…" hint="Large selections take a few seconds." />
            </div>
          )}
          {status && <p className={"tf-status is-" + statusTone} role="status">{status}</p>}
        </aside>
      </form>
    </div>
  );
}
