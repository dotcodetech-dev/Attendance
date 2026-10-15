import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { DirectionBadge } from "../components/DirectionBadge";
import { formatDeviceIST, formatIST } from "../utils/datetime";

/** Face-recognition attendance: camera monitor + photo enrollment. */
export function FaceAttendancePage() {
  const [camera, setCamera] = useState<any>(null);
  const [punches, setPunches] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [summary, setSummary] = useState<Record<string, { count: number; last: string | null }>>({});

  const [selectedCode, setSelectedCode] = useState("");
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [enrollments, setEnrollments] = useState<any[]>([]);
  const [enrolling, setEnrolling] = useState(false);
  const [note, setNote] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Preview-then-confirm: hold the candidate image + its measured quality
  // before it is enrolled.
  const [preview, setPreview] = useState<
    { image: string; file: File; detScore: number; faceCount: number; source: "camera" | "upload" } | null
  >(null);
  const [previewBusy, setPreviewBusy] = useState(false);

  const loadCamera = () => api.getCameraStatus().then(setCamera).catch(() => setCamera(null));
  const loadPunches = () => api.getFacePunches(20).then(setPunches).catch(() => {});
  const loadSummary = () =>
    api.getFaceEnrollmentSummary().then((rows: any[]) => {
      const map: Record<string, { count: number; last: string | null }> = {};
      rows.forEach((r) => { map[r.employee_code] = { count: r.count, last: r.last_enrolled_at }; });
      setSummary(map);
    }).catch(() => {});

  useEffect(() => {
    loadCamera();
    loadPunches();
    loadSummary();
    api.getEmployees().then(setEmployees).catch(() => setEmployees([]));
    const statusTimer = window.setInterval(loadCamera, 5000);
    const punchTimer = window.setInterval(loadPunches, 10000);
    return () => { window.clearInterval(statusTimer); window.clearInterval(punchTimer); };
  }, []);

  useEffect(() => {
    if (!selectedCode) { setEnrollments([]); return; }
    api.getFaceEnrollments(selectedCode).then(setEnrollments).catch(() => setEnrollments([]));
  }, [selectedCode]);

  const finishEnroll = async (res: any) => {
    setNote(
      `Enrolled ${res.employee_name} (photo quality ${Math.round(res.det_score * 100)}%). ` +
      `${res.enrolled_count} photo(s) on file. 2-3 photos per person is ideal.`
    );
    await Promise.all([
      api.getFaceEnrollments(selectedCode).then(setEnrollments),
      loadSummary(),
    ]);
  };

  const dataUrlToFile = async (dataUrl: string, name: string): Promise<File> => {
    const blob = await (await fetch(dataUrl)).blob();
    return new File([blob], name, { type: "image/jpeg" });
  };

  // --- Preview step: measure quality, show image, wait for confirm ---
  const previewFromCamera = async () => {
    if (!selectedCode) { setNote("Select an employee first."); return; }
    setPreview(null);
    setPreviewBusy(true);
    setNote("Capturing live camera frame… make sure the employee is facing the camera.");
    try {
      const res = await api.previewCameraFrame();
      const file = await dataUrlToFile(res.image, `camera-${selectedCode}.jpg`);
      setPreview({ image: res.image, file, detScore: res.det_score, faceCount: res.face_count, source: "camera" });
      setNote("");
    } catch (e: any) {
      setNote(`Capture failed: ${e?.message || e}`);
    } finally {
      setPreviewBusy(false);
    }
  };

  const previewFromUpload = async (file: File) => {
    if (!selectedCode) { setNote("Select an employee first."); return; }
    setPreview(null);
    setPreviewBusy(true);
    setNote("Checking photo quality…");
    try {
      const res = await api.previewPhoto(file);
      const image = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.readAsDataURL(file);
      });
      setPreview({ image, file, detScore: res.det_score, faceCount: res.face_count, source: "upload" });
      setNote("");
    } catch (e: any) {
      setNote(`Photo check failed: ${e?.message || e}`);
    } finally {
      setPreviewBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // --- Confirm step: enroll the previewed image ---
  const confirmEnroll = async () => {
    if (!preview || !selectedCode) return;
    setEnrolling(true);
    setNote("Enrolling…");
    try {
      await finishEnroll(await api.enrollFace(selectedCode, preview.file));
      setPreview(null);
    } catch (e: any) {
      setNote(`Enrollment failed: ${e?.message || e}`);
    } finally {
      setEnrolling(false);
    }
  };

  const removeEnrollment = async (id: number) => {
    try {
      await api.deleteFaceEnrollment(id);
      setEnrollments((rows) => rows.filter((r) => r.embedding_id !== id));
      loadSummary();
      setNote("Enrollment removed.");
    } catch (e: any) {
      setNote(`Delete failed: ${e?.message || e}`);
    }
  };

  const svc = camera?.status;
  const cameraOnline = Boolean(camera?.reachable && svc?.camera_connected);
  const filteredEmployees = employees.filter((e) => {
    const q = employeeSearch.trim().toLowerCase();
    if (!q) return true;
    return String(e.EmployeeName || "").toLowerCase().includes(q) || String(e.EmployeeCode || "").includes(q);
  });

  const StatusPill = ({ ok, okLabel, badLabel }: { ok: boolean; okLabel: string; badLabel: string }) => (
    <span className={"badge " + (ok ? "badge-green" : "badge-gray")}>{ok ? okLabel : badLabel}</span>
  );

  const PreviewPanel = () => {
    if (!preview) return null;
    const pct = Math.round((preview.detScore || 0) * 100);
    // det_score bands: >=70 strong, 55-70 usable, <55 weak.
    const band = pct >= 70 ? "green" : pct >= 55 ? "amber" : "red";
    const barColor = band === "green" ? "#16a34a" : band === "amber" ? "#d97706" : "#dc2626";
    const qualityLabel = band === "green" ? "Good" : band === "amber" ? "Usable" : "Poor — retake if you can";
    const oneFace = preview.faceCount === 1;
    return (
      <div style={{ marginTop: 12, padding: 16, border: "1px solid var(--border)", borderRadius: 10, background: "var(--surface)" }}>
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "flex-start" }}>
          <img
            src={preview.image}
            alt="capture preview"
            style={{ width: 220, height: 220, objectFit: "cover", borderRadius: 8, border: `3px solid ${barColor}` }}
          />
          <div style={{ flex: 1, minWidth: 220 }}>
            <h4 style={{ margin: "0 0 4px" }}>
              Preview — {preview.source === "camera" ? "captured from camera" : "selected photo"}
            </h4>
            <p style={{ margin: "0 0 10px", color: "var(--text-muted)", fontSize: 13 }}>
              Enrolling for <strong>{employees.find((e) => e.EmployeeCode === selectedCode)?.EmployeeName || selectedCode}</strong>.
              Confirm only if the face is clear and well-lit.
            </p>

            <div style={{ fontSize: 13, marginBottom: 4 }}>
              Image quality: <strong>{pct}%</strong> <span style={{ color: barColor }}>({qualityLabel})</span>
            </div>
            <div style={{ height: 10, background: "var(--border)", borderRadius: 6, overflow: "hidden", maxWidth: 320 }}>
              <div style={{ width: `${pct}%`, height: "100%", background: barColor }} />
            </div>

            <div style={{ marginTop: 10, fontSize: 13 }}>
              {preview.faceCount === 0
                ? <span className="badge badge-gray">No face detected</span>
                : oneFace
                  ? <span className="badge badge-green">1 face detected</span>
                  : <span className="badge badge-gray">{preview.faceCount} faces — only the largest will be enrolled</span>}
            </div>

            <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
              <button className="btn btn-primary-purple" disabled={enrolling || preview.faceCount === 0} onClick={confirmEnroll}>
                {enrolling ? "Enrolling…" : "Confirm & Enroll"}
              </button>
              <button
                className="btn btn-outline-reports"
                disabled={enrolling || previewBusy}
                onClick={() => (preview.source === "camera" ? previewFromCamera() : fileInputRef.current?.click())}
              >
                {preview.source === "camera" ? "Retake" : "Choose Another"}
              </button>
              <button className="btn btn-outline-reports" disabled={enrolling} onClick={() => { setPreview(null); setNote(""); }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Face Attendance</h2>
          <p className="sub">Camera-based face recognition: monitor the entry camera and enroll employee photos.</p>
        </div>
      </div>

      {/* ---- Camera status ---- */}
      <div className="section-card">
        <h3>Camera Monitor <span className="badge badge-blue">auto-refresh</span></h3>
        {!camera ? (
          <p style={{ color: "var(--text-muted)" }}>Loading status…</p>
        ) : (
          <>
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
              <div><strong>Service</strong>{" "}
                <StatusPill ok={camera.reachable} okLabel="Running" badLabel="Unreachable" />
              </div>
              <div><strong>Camera</strong>{" "}
                {svc?.camera_configured === false
                  ? <span className="badge badge-gray">Not configured</span>
                  : <StatusPill ok={cameraOnline} okLabel="Connected" badLabel="Offline" />}
              </div>
              <div><strong>Model</strong>{" "}
                <StatusPill ok={Boolean(svc?.model_loaded)} okLabel="Loaded" badLabel="Not loaded" />
              </div>
              <div><strong>Gallery</strong> {svc ? `${svc.gallery_size} embedding(s)` : "—"}</div>
              <div><strong>Punches posted</strong> {svc ? svc.punches_posted : "—"}</div>
              {svc?.punches_pending > 0 && (
                <div><span className="badge badge-gray">{svc.punches_pending} punch(es) queued</span></div>
              )}
            </div>
            {!camera.reachable && (
              <p className="note-err">
                Camera service is not running at {camera.service_url}. Start it from Aveon/camera_service:
                venv\Scripts\python -m uvicorn app.main:app --port 8100
              </p>
            )}
            {camera.reachable && svc?.camera_configured === false && (
              <p className="note-err">Camera credentials are not set. Fill CAMERA_HOST / CAMERA_USER / CAMERA_PASSWORD in camera_service/.env and restart the service.</p>
            )}
            {svc?.gallery_last_sync_error && (
              <p className="note-err">Gallery sync error: {svc.gallery_last_sync_error}</p>
            )}
            {svc?.punch_post_error && (
              <p className="note-err">Punch delivery error: {svc.punch_post_error}</p>
            )}
            {svc?.last_match && (
              <p style={{ color: "var(--text-muted)", fontSize: 13, margin: 0 }}>
                Last match: <strong>{svc.last_match.employee_name}</strong> ({svc.last_match.employee_code}),
                similarity {svc.last_match.similarity}
              </p>
            )}
          </>
        )}
      </div>

      {/* ---- Recent recognitions ---- */}
      <div className="section-card">
        <h3>Recent Recognitions</h3>
        <div className="table-scroll" style={{ maxHeight: 380, overflowY: "auto" }}>
          <table className="table table-compact">
            <thead>
              <tr><th>Snapshot</th><th>Employee</th><th>Time</th><th>Direction</th><th>Match</th><th>Camera</th></tr>
            </thead>
            <tbody>
              {punches.length === 0 ? (
                <tr><td colSpan={6} style={{ color: "var(--text-muted)", padding: "24px 12px" }}>
                  No face punches yet. They appear here as soon as the camera recognizes an enrolled employee.
                </td></tr>
              ) : punches.map((p) => (
                <tr key={p.log_id}>
                  <td>
                    {p.snapshot
                      ? <img src={p.snapshot} alt="" style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 6 }} />
                      : <span className="badge badge-gray">No photo</span>}
                  </td>
                  <td><strong>{p.employee_name || p.employee_code}</strong>
                    <div style={{ color: "var(--text-muted)", fontSize: 12 }}>{p.employee_code}</div>
                  </td>
                  <td>{formatDeviceIST(p.log_date)}</td>
                  <td><DirectionBadge value={p.direction} /></td>
                  <td>{p.similarity || "-"}</td>
                  <td>{p.device_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ---- Enrollment ---- */}
      <div className="section-card">
        <h3>Face Enrollment</h3>
        <p style={{ marginTop: 0, color: "var(--text-muted)", fontSize: 13 }}>
          Capture 2-3 shots per employee — either upload a photo or have them face the entry camera and
          click <strong>Capture from Camera</strong>. You'll see a preview and a quality score before it's
          saved. Camera captures match best, because they share the camera's angle and lighting.
        </p>
        <div className="toolbar">
          <div className="field">
            <label>Search</label>
            <input
              type="search"
              placeholder="Name or code…"
              value={employeeSearch}
              onChange={(e) => setEmployeeSearch(e.target.value)}
            />
          </div>
          <div className="field">
            <label>Employee</label>
            <select value={selectedCode} onChange={(e) => setSelectedCode(e.target.value)}>
              <option value="">Select employee…</option>
              {filteredEmployees.map((e) => (
                <option key={e.EmployeeId} value={e.EmployeeCode}>
                  {e.EmployeeName} · {e.EmployeeCode}
                  {summary[e.EmployeeCode] ? ` (${summary[e.EmployeeCode].count} enrolled)` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="toolbar-actions">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png"
              style={{ display: "none" }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) previewFromUpload(f); }}
            />
            <button
              className="btn btn-primary-purple"
              disabled={!selectedCode || previewBusy || enrolling}
              onClick={() => fileInputRef.current?.click()}
            >
              Choose Photo…
            </button>
            <button
              className="btn btn-outline-reports"
              disabled={!selectedCode || previewBusy || enrolling || !cameraOnline}
              title={cameraOnline ? "Employee stands facing the camera, then click" : "Camera is offline"}
              onClick={previewFromCamera}
            >
              {previewBusy && preview === null ? "Capturing…" : "Capture from Camera"}
            </button>
          </div>
        </div>

        {note && <p className={note.toLowerCase().includes("fail") ? "note-err" : "note-ok"}>{note}</p>}

        {preview && <PreviewPanel />}

        {selectedCode && (
          <div className="table-scroll" style={{ marginTop: 8 }}>
            <table className="table table-compact">
              <thead>
                <tr><th>ID</th><th>Photo Quality</th><th>Enrolled At</th><th>Source</th><th></th></tr>
              </thead>
              <tbody>
                {enrollments.length === 0 ? (
                  <tr><td colSpan={5} style={{ color: "var(--text-muted)" }}>
                    No face photos enrolled for this employee yet.
                  </td></tr>
                ) : enrollments.map((r) => (
                  <tr key={r.embedding_id}>
                    <td>{r.embedding_id}</td>
                    <td>{r.det_score != null ? `${Math.round(r.det_score * 100)}%` : "-"}</td>
                    <td>{r.created_at ? formatIST(r.created_at) : "-"}</td>
                    <td>{r.source || "-"}</td>
                    <td>
                      <button className="btn btn-outline-reports" onClick={() => removeEnrollment(r.embedding_id)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
