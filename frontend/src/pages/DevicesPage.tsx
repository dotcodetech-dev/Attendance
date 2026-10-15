import { FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { ConfigModal, Flash, SectionHead, Segmented } from "../components/ConfigUi";
import { BtnSpinner, LoadingNote, SkeletonRows } from "../components/LoadingNote";
import { Icons } from "../components/SidebarIcons";
import { TemplateCells, templateTotals } from "../components/TemplateCells";
import { Req } from "../components/Req";
import { useCampusOrg } from "../store/me";
import { formatIST, timeAgoIST } from "../utils/datetime";

const DEVICE_TYPES: { value: string; label: string }[] = [
  { value: "AI", label: "AI Face Reader" },
  { value: "FP", label: "Fingerprint" },
  { value: "Card", label: "Card Reader" },
  { value: "Camera", label: "IP Camera" },
];

const DIRECTIONS: [string, string][] = [["IN", "IN only"], ["OUT", "OUT only"], ["INOUT", "IN / OUT"]];
const directionLabel = (v: unknown) => DIRECTIONS.find(([k]) => k === String(v || "").toUpperCase())?.[1] ?? (String(v || "") || "—");

function deviceTypeLabel(value: unknown): string {
  const v = String(value || "").trim();
  const hit = DEVICE_TYPES.find((t) => t.value.toLowerCase() === v.toLowerCase());
  return hit ? hit.label : v || "Device";
}

const isOnlineRow = (row: any) => (row.DeviceStatus || "").toString().toLowerCase() === "online";

type DeviceForm = {
  DeviceName: string;
  SerialNumber: string;
  DeviceIPAddress: string;
  DeviceDirection: string;
  DeviceType: string;
  Port: string;
  CommKey: string;
  OrganizationId: string;   // institution ("" = not set); campus-role logins see only their institution's readers
};

const EMPTY_FORM: DeviceForm = {
  DeviceName: "",
  SerialNumber: "",
  DeviceIPAddress: "",
  DeviceDirection: "INOUT",
  DeviceType: "AI",
  Port: "4370",
  CommKey: "",
  OrganizationId: "",
};

type DetailState = {
  testing: boolean;
  testResult: string;
  testOk: boolean | null;
  fetching: boolean;
  fetchResult: string;
  commLog: any[];
  commStatus: string;
};

const EMPTY_DETAIL: DetailState = {
  testing: false,
  testResult: "",
  testOk: null,
  fetching: false,
  fetchResult: "",
  commLog: [],
  commStatus: "",
};

export function DevicesPage() {
  const navigate = useNavigate();
  // A campus-role login sees only its institution's readers (the server filters them) and new readers join it.
  const campus = useCampusOrg();
  const [organizations, setOrganizations] = useState<{ OrganizationId: number; OrgName: string }[]>([]);
  useEffect(() => { api.getOrganizations().then(setOrganizations).catch(() => setOrganizations([])); }, []);
  const orgNameOf = (id: number | null | undefined) => organizations.find((o) => o.OrganizationId === id)?.OrgName || "";
  const [rows, setRows] = useState<any[]>([]);
  const [blocked, setBlocked] = useState<any[]>([]);   // Face IDs of deleted people the readers may still send
  const [devicesLoaded, setDevicesLoaded] = useState(false);   // so "No devices yet" is not shown while they are still loading
  const [filter, setFilter] = useState<"all" | "online" | "offline">("all");
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);

  // Add / edit popup
  const [modal, setModal] = useState<"add" | "edit" | null>(null);
  const [editingDeviceId, setEditingDeviceId] = useState<number | null>(null);
  const [form, setForm] = useState<DeviceForm>({ ...EMPTY_FORM });
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [sdkStatus, setSdkStatus] = useState("");
  const [sdkStatusOk, setSdkStatusOk] = useState<boolean | null>(null);

  // Connectivity details panel (one device open at a time)
  const [detailsDeviceId, setDetailsDeviceId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DetailState>(EMPTY_DETAIL);

  // Machine users panel
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [deviceUsers, setDeviceUsers] = useState<any[]>([]);
  const [usersStatus, setUsersStatus] = useState("");
  const [usersError, setUsersError] = useState(false);
  // What the panel is waiting on: reading the list, a reader asked to re-send (with a countdown), or reloading.
  const [usersMode, setUsersMode] = useState<"" | "read" | "refresh" | "reload">("");
  const [reloadIn, setReloadIn] = useState(0);
  const usersReq = useRef(0);                         // ignores a late answer for a panel that was closed or switched
  const reloadTimer = useRef<number | null>(null);
  const [deletingUserKey, setDeletingUserKey] = useState("");
  const [photoActionKey, setPhotoActionKey] = useState("");
  const [selectedPhoto, setSelectedPhoto] = useState<{
    employeeCode: string;
    photoData: string;
    photoMimeType?: string;
    source?: string;
  } | null>(null);

  useEffect(() => { api.getBlockedPins().then(setBlocked).catch(() => setBlocked([])); }, []);
  const load = () => api.getDevices().then(setRows).catch(() => setRows([])).finally(() => setDevicesLoaded(true));
  useEffect(() => {
    load();
  }, []);

  const onlineCount = rows.filter(isOnlineRow).length;
  const offlineCount = rows.length - onlineCount;
  const shown = rows.filter((r) => filter === "all" || (filter === "online") === isOnlineRow(r));

  // ----- Add / edit -----
  const openAdd = () => {
    setEditingDeviceId(null);
    setForm({ ...EMPTY_FORM });
    setFormError("");
    setSdkStatus("");
    setSdkStatusOk(null);
    setModal("add");
  };

  const openEdit = (row: any) => {
    setEditingDeviceId(row.DeviceId);
    setForm({
      DeviceName: row.DeviceName || "",
      SerialNumber: row.SerialNumber || "",
      DeviceIPAddress: row.DeviceIPAddress || "",
      DeviceDirection: row.DeviceDirection || "IN",
      DeviceType: row.DeviceType || "AI",
      Port: "4370",
      CommKey: row.CommKey != null ? String(row.CommKey) : "",
      OrganizationId: row.OrganizationId != null ? String(row.OrganizationId) : "",
    });
    setFormError("");
    setSdkStatus("");
    setSdkStatusOk(null);
    setModal("edit");
  };

  const closeModal = () => { setModal(null); setEditingDeviceId(null); setFormError(""); };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setFormError("");
    if (!form.DeviceName.trim()) { setFormError("Enter a device name."); return; }
    if (modal === "add" && !form.SerialNumber.trim()) { setFormError("Enter the serial number."); return; }
    if (!form.DeviceIPAddress.trim()) { setFormError("Enter the IP address."); return; }
    setSaving(true);
    try {
      if (modal === "edit" && editingDeviceId !== null) {
        await api.updateDevice(editingDeviceId, {
          DeviceName: form.DeviceName.trim(),
          DeviceIPAddress: form.DeviceIPAddress.trim(),
          DeviceDirection: form.DeviceDirection,
          DeviceType: form.DeviceType,
          CommKey: form.CommKey.trim() ? Number(form.CommKey) : null,
          OrganizationId: form.OrganizationId ? Number(form.OrganizationId) : null,
        });
        setStatus({ text: "Device updated.", ok: true });
      } else {
        const { Port, CommKey, OrganizationId, ...deviceFields } = form;
        await api.createDevice({ ...deviceFields, CommKey: CommKey.trim() ? Number(CommKey) : null,
          OrganizationId: OrganizationId ? Number(OrganizationId) : null });
        setStatus({ text: `${form.DeviceName.trim()} added.`, ok: true });
      }
      closeModal();
      await load();
    } catch (err) {
      setFormError((err as Error).message || "Could not save the device.");
    } finally {
      setSaving(false);
    }
  };

  const testSdkConnection = async () => {
    if (!form.DeviceIPAddress.trim()) {
      setSdkStatus("Enter the device IP address first.");
      setSdkStatusOk(false);
      return;
    }
    setSdkStatus("Testing SDK connection…");
    setSdkStatusOk(null);
    try {
      const port = parseInt(form.Port, 10) || 4370;
      const result = await api.testDeviceConnection(form.DeviceIPAddress, port, form.CommKey.trim() ? Number(form.CommKey) : undefined);
      setSdkStatus(
        result.connected
          ? `Connected over SDK (${result.prog_id || "zkemkeeper"}) at ${form.DeviceIPAddress}:${port}`
          : `Not reachable: ${result.message || "Unknown error"}`
      );
      setSdkStatusOk(!!result.connected);
    } catch (err) {
      setSdkStatus(`SDK test failed: ${(err as Error).message}`);
      setSdkStatusOk(false);
    }
  };

  const connectDevice = async (deviceId: number) => {
    setStatus({ text: "Connecting device…", ok: true });
    try {
      const result = await api.connectDevice(deviceId);
      setStatus({
        text: result.connected
          ? `Device connected. Status: ${result.DeviceStatus || "Online"}`
          : `Connect failed: ${result.message || "Unknown error"}`,
        ok: !!result.connected,
      });
      load();
    } catch (err) {
      setStatus({ text: `Connect failed: ${(err as Error).message}`, ok: false });
    }
  };

  const deleteDevice = (row: any) => {
    if (window.confirm(`Delete device "${row.DeviceName}"? This does not remove already-stored punches.`)) {
      api.deleteDevice(row.DeviceId).then(() => { setStatus({ text: "Device deleted.", ok: true }); load(); })
        .catch((e) => setStatus({ text: e?.message || "Could not delete the device.", ok: false }));
    }
  };

  // ----- Connectivity details panel -----
  const toggleDetails = (row: any) => {
    if (detailsDeviceId === row.DeviceId) {
      setDetailsDeviceId(null);
      setDetail(EMPTY_DETAIL);
      return;
    }
    setDetailsDeviceId(row.DeviceId);
    setDetail(EMPTY_DETAIL);
    loadCommLog(row);
  };

  const loadCommLog = async (row: any) => {
    setDetail((d) => ({ ...d, commStatus: "Loading recent activity…", commLog: [] }));
    try {
      const log = await api.getDeviceCommLog(row.SerialNumber, 40);
      setDetail((d) => ({
        ...d,
        commLog: Array.isArray(log) ? log : [],
        commStatus: (Array.isArray(log) && log.length) ? "" : "No recent communication recorded.",
      }));
    } catch (err) {
      setDetail((d) => ({ ...d, commStatus: `Could not load activity: ${(err as Error).message}` }));
    }
  };

  const testDeviceInPanel = async (row: any) => {
    setDetail((d) => ({ ...d, testing: true, testResult: "", testOk: null }));
    try {
      // Device-aware test: SDK when reachable, otherwise reports the Cloud/ADMS push status.
      const result = await api.connectDevice(row.DeviceId);
      setDetail((d) => ({
        ...d,
        testing: false,
        testOk: !!result.connected,
        testResult: result.connected
          ? (result.prog_id === "push" ? result.message : `Reachable over SDK (${result.prog_id || "zkemkeeper"})`)
          : `Not reachable: ${result.message || "Unknown error"}`,
      }));
    } catch (err) {
      setDetail((d) => ({ ...d, testing: false, testOk: false, testResult: `Test failed: ${(err as Error).message}` }));
    }
  };

  const fetchAttendance = async (row: any) => {
    setDetail((d) => ({ ...d, fetching: true, fetchResult: "Pulling punches from device over SDK…" }));
    try {
      const result = await api.fetchDeviceAttendance(row.DeviceId);
      if (result.connected) {
        setDetail((d) => ({
          ...d,
          fetching: false,
          fetchResult: `Fetched ${result.fetched} record(s); ${result.inserted} new stored.`,
        }));
      } else {
        setDetail((d) => ({ ...d, fetching: false, fetchResult: result.message || "Could not connect over SDK." }));
      }
      loadCommLog(row);
      load();
    } catch (err) {
      setDetail((d) => ({ ...d, fetching: false, fetchResult: `Fetch failed: ${(err as Error).message}` }));
    }
  };

  // ----- Machine users panel -----
  const stopReloadTimer = () => {
    if (reloadTimer.current !== null) { window.clearInterval(reloadTimer.current); reloadTimer.current = null; }
    setReloadIn(0);
  };
  useEffect(() => () => { if (reloadTimer.current !== null) window.clearInterval(reloadTimer.current); }, []);

  const closeUsers = () => {
    usersReq.current += 1;
    stopReloadTimer();
    setReaderStatus(null);
    setSelectedDeviceId(null);
    setDeviceUsers([]);
    setUsersStatus("");
    setUsersError(false);
    setUsersMode("");
    setRefreshingUsers(false);
  };

  // What the server knows about a push reader: last poll, users on record, last refresh (explains an empty list).
  const [readerStatus, setReaderStatus] = useState<any>(null);
  const loadReaderStatus = (deviceId: number) =>
    api.getReaderStatus(deviceId).then((s) => { setReaderStatus(s); return s; }).catch(() => { setReaderStatus(null); return null; });

  const emptyListNote = (s: any) => {
    if (!s) return "No users known for this device yet. If it is a remote (push) reader, use Refresh from device.";
    if (s.last_refresh && (s.last_refresh.status === "Pending" || s.last_refresh.status === "Sent"))
      return `No users yet. A refresh was asked for and is ${s.last_refresh.status === "Pending" ? "waiting for the reader to poll" : "with the reader"}; `
        + `the reader last polled ${s.last_poll_text}. Its users appear once it answers.`;
    if (!s.polling)
      return `No users yet, and the reader last polled ${s.last_poll_text}. Check its network and its Cloud Server / ADMS setting, then use Refresh from device.`;
    return "No users on record for this reader yet. Use Refresh from device to ask it for its user list.";
  };

  const loadUsers = async (deviceId: number) => {
    usersReq.current += 1;
    const req = usersReq.current;
    stopReloadTimer();
    setSelectedDeviceId(deviceId);
    setDeviceUsers([]);
    setUsersStatus("");
    setUsersError(false);
    setUsersMode("read");
    setReaderStatus(null);
    const statusP = loadReaderStatus(deviceId);
    try {
      const users = await api.getDeviceMachineUsers(deviceId);
      if (req !== usersReq.current) return;
      setDeviceUsers(users);
      const viaPush = users.length > 0 && users[0].Source === "push";
      const status = users.length === 0 ? await statusP : null;
      if (req !== usersReq.current) return;
      setUsersStatus(users.length === 0
        ? emptyListNote(status)
        : viaPush ? "Remote reader (Cloud/ADMS push): showing the users it has sent to this server. Use Refresh from device to re-read them." : "");
    } catch (err) {
      if (req !== usersReq.current) return;
      setDeviceUsers([]);
      setUsersError(true);
      setUsersStatus(`Failed to read machine users: ${(err as Error).message}`);
    } finally {
      if (req === usersReq.current) setUsersMode("");
    }
  };

  const showDeviceUsers = (deviceId: number) => {
    if (selectedDeviceId === deviceId) { closeUsers(); return; }
    loadUsers(deviceId);
  };

  const [refreshingUsers, setRefreshingUsers] = useState(false);
  const [refreshCount, setRefreshCount] = useState<number | null>(null);   // users seen so far while waiting
  // A reader answers a refresh over its next polls; a slow or briefly quiet one takes longer than a fixed 30 s.
  // Re-read the list every 10 s for up to 2 minutes; finish early once users have arrived and the count holds steady.
  const REFRESH_WAIT_SECONDS = 120;
  const REFRESH_CHECK_EVERY = 10;
  const refreshUsersFromDevice = async (deviceId: number) => {
    usersReq.current += 1;
    const req = usersReq.current;
    stopReloadTimer();
    setRefreshingUsers(true);
    setUsersError(false);
    setUsersStatus("");
    setRefreshCount(null);
    setUsersMode("refresh");
    const finish = (users: any[] | null, note: string, isError = false) => {
      stopReloadTimer();
      if (req !== usersReq.current) return;
      if (users) setDeviceUsers(users);
      setUsersError(isError);
      setUsersStatus(note);
      setUsersMode("");
      setRefreshingUsers(false);
      setRefreshCount(null);
      loadReaderStatus(deviceId);
    };
    try {
      const queued: any = await api.refreshDeviceMachineUsers(deviceId);
      if (req !== usersReq.current) return;
      setReloadIn(REFRESH_WAIT_SECONDS);
      let left = REFRESH_WAIT_SECONDS;
      let lastCount = -1;
      let checking = false;
      reloadTimer.current = window.setInterval(async () => {
        left -= 1;
        if (req !== usersReq.current) { stopReloadTimer(); return; }
        setReloadIn(left);
        if ((REFRESH_WAIT_SECONDS - left) % REFRESH_CHECK_EVERY !== 0 && left > 0) return;
        if (checking) return;
        checking = true;
        try {
          const users = await api.getDeviceMachineUsers(deviceId);
          if (req !== usersReq.current) return;
          setDeviceUsers(users);
          setRefreshCount(users.length);
          const steady = users.length > 0 && users.length === lastCount;
          lastCount = users.length;
          if (steady || left <= 0) {
            if (users.length > 0) {
              finish(users, `Refreshed: ${users.length} user(s) known for this reader.`);
            } else {
              const s = await loadReaderStatus(deviceId);
              finish(users, s && !s.polling
                ? `The reader has not answered yet: it last polled ${s.last_poll_text}. The refresh stays queued; open Users again later. ${queued?.message || ""}`.trim()
                : "The reader has not sent any users yet. It may still be answering; open Users again in a minute.");
            }
          }
        } catch (e) {
          finish(null, `Reload failed: ${(e as Error).message}`, true);
        } finally {
          checking = false;
        }
      }, 1000);
    } catch (err) {
      if (req !== usersReq.current) return;
      setUsersError(true);
      setUsersStatus(`Refresh failed: ${(err as Error).message}`);
      setUsersMode("");
      setRefreshingUsers(false);
    }
  };

  const [sendingNames, setSendingNames] = useState(false);
  const sendNames = async (deviceId: number) => {
    setSendingNames(true);
    setUsersError(false);
    setUsersStatus("Sending names to the reader…");
    try {
      const r = await api.sendNamesToDevice(deviceId);
      setUsersStatus(r.message);
    } catch (err) {
      setUsersError(true);
      setUsersStatus(`Send names failed: ${(err as Error).message}`);
    } finally {
      setSendingNames(false);
    }
  };

  const deleteDeviceUser = async (deviceId: number, employeeCode: string) => {
    const cleanCode = String(employeeCode || "").trim();
    if (!cleanCode) {
      setUsersStatus("Employee code is missing.");
      return;
    }
    if (!window.confirm(`Delete user ${cleanCode} from device ${deviceId}?`)) {
      return;
    }
    const opKey = `${deviceId}-${cleanCode}`;
    setDeletingUserKey(opKey);
    setUsersStatus(`Deleting user ${cleanCode} from device…`);
    try {
      const result = await api.deleteDeviceMachineUser(deviceId, cleanCode);
      setUsersMode("reload");
      const users = await api.getDeviceMachineUsers(deviceId);
      setDeviceUsers(users);
      const stillExists = users.some((user: any) => {
        const left = String(user.EmployeeCode || "").trim();
        const right = cleanCode;
        if (left === right) return true;
        if (/^\d+$/.test(left) && /^\d+$/.test(right)) return Number(left) === Number(right);
        return false;
      });
      if (result.deleted || !stillExists) {
        setUsersStatus(`User ${cleanCode} deleted successfully from device.`);
        await load();
      } else {
        setUsersStatus(result.message || `Could not delete user ${cleanCode} from device.`);
        await load();
      }
    } catch (err) {
      setUsersStatus(`Delete failed: ${(err as Error).message}`);
    } finally {
      setDeletingUserKey("");
      setUsersMode((m) => (m === "reload" && reloadTimer.current === null ? "" : m));
    }
  };

  const buildPhotoSrc = (photoData: string, mimeType?: string) => {
    if (!photoData) return "";
    if (photoData.startsWith("data:")) return photoData;
    return `data:${mimeType || "image/jpeg"};base64,${photoData}`;
  };

  const fetchUserPhoto = async (deviceId: number, employeeCode: string) => {
    const cleanCode = String(employeeCode || "").trim();
    if (!cleanCode) return;
    const opKey = `fetch-${deviceId}-${cleanCode}`;
    setPhotoActionKey(opKey);
    setUsersStatus(`Fetching photo for user ${cleanCode} from device…`);
    try {
      const result = await api.pullDeviceUserPhoto(deviceId, cleanCode);
      setUsersStatus(
        result.photo_found
          ? `Photo synced for user ${cleanCode}.`
          : result.message || `Photo not found for user ${cleanCode} on device.`
      );
    } catch (err) {
      setUsersStatus(`Photo fetch failed: ${(err as Error).message}`);
    } finally {
      setPhotoActionKey("");
    }
  };

  const viewUserPhoto = async (employeeCode: string) => {
    const cleanCode = String(employeeCode || "").trim();
    if (!cleanCode) return;
    const opKey = `view-${selectedDeviceId}-${cleanCode}`;
    setPhotoActionKey(opKey);
    setUsersStatus(`Loading photo for user ${cleanCode}…`);
    try {
      const result = await api.getEmployeePhoto(cleanCode, true);
      if (!result?.HasPhoto || !result?.PhotoData) {
        setUsersStatus(`No stored photo found for user ${cleanCode}. Use Fetch Photo first.`);
        return;
      }
      setSelectedPhoto({
        employeeCode: cleanCode,
        photoData: result.PhotoData,
        photoMimeType: result.PhotoMimeType,
        source: result.Source,
      });
      setUsersStatus("");
    } catch (err) {
      setUsersStatus(`Photo load failed: ${(err as Error).message}`);
    } finally {
      setPhotoActionKey("");
    }
  };

  const detailRow = rows.find((r) => r.DeviceId === detailsDeviceId);
  const usersRow = rows.find((r) => r.DeviceId === selectedDeviceId);

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Devices</h2>
          <p className="sub">Biometric readers and cameras. Attendance is pulled from readers automatically every 10 minutes over the SDK. Readers can also <strong>push over Cloud/ADMS</strong> — point the reader's Cloud Server at this server (port 80) and attendance arrives automatically, with no SDK or port 4370 needed.</p>
        </div>
        <button type="button" className="btn btn-primary-purple" onClick={openAdd}>+ Add device</button>
      </div>

      <Flash status={status} />

      <div className="cfg-stats">
        <button type="button" className={"cfg-stat" + (filter === "all" ? " on" : "")} onClick={() => setFilter("all")} aria-pressed={filter === "all"}>
          <b>{rows.length}</b><span>All devices</span>
        </button>
        <button type="button" className={"cfg-stat stat-online" + (filter === "online" ? " on" : "")} onClick={() => setFilter(filter === "online" ? "all" : "online")} aria-pressed={filter === "online"}>
          <b>{onlineCount}</b><span>Online</span>
        </button>
        <button type="button" className={"cfg-stat stat-offline" + (filter === "offline" ? " on" : "")} onClick={() => setFilter(filter === "offline" ? "all" : "offline")} aria-pressed={filter === "offline"}>
          <b>{offlineCount}</b><span>Offline</span>
        </button>
      </div>

      {blocked.length > 0 && (
        <div className="section-card" style={{ marginBottom: 14 }}>
          <h3 style={{ marginTop: 0 }}>Blocked IDs <span className="badge badge-gray">{blocked.length}</span></h3>
          <p className="sub">Face IDs of people deleted here. A reader may still send them; nothing is stored and no staff record is created. Use “Allow again” before re-adding such a person.</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {blocked.map((b: any) => (
              <span key={b.Pin} className="badge badge-gray" style={{ display: "inline-flex", gap: 8, alignItems: "center", padding: "4px 8px" }}>
                <strong>{b.Pin}</strong>{b.EmployeeName ? ` ${b.EmployeeName}` : ""}
                <button type="button" className="btn-outline-reports" style={{ padding: "0 8px", height: 24 }}
                        onClick={() => api.allowPinAgain(b.Pin).then(() => setBlocked((cur) => cur.filter((x: any) => x.Pin !== b.Pin)))}>Allow again</button>
              </span>
            ))}
          </div>
        </div>
      )}

      {!devicesLoaded ? (
        <div className="section-card"><LoadingNote message="Loading devices…" /><SkeletonRows count={3} /></div>
      ) : rows.length === 0 ? (
        <div className="section-card cfg-empty">
          <strong>No devices yet</strong>
          <span>Add a reader or camera to start collecting attendance.</span>
          <button type="button" className="btn btn-primary-purple" onClick={openAdd}>+ Add device</button>
        </div>
      ) : shown.length === 0 ? (
        <div className="section-card cfg-empty"><strong>No {filter} devices</strong><span>Choose All devices to see every one.</span></div>
      ) : (
        <div className="dev-grid">
          {shown.map((row) => {
            const online = isOnlineRow(row);
            const isCamera = (row.DeviceType || "").toString().toLowerCase() === "camera";
            const detailsOpen = detailsDeviceId === row.DeviceId;
            const usersOpen = selectedDeviceId === row.DeviceId;
            return (
              <article key={row.DeviceId} className={"dev-card " + (online ? "is-online" : "is-offline")}>
                <header className="dev-head">
                  <div className="dev-title">
                    <h3>{row.DeviceName}</h3>
                    <span className="device-type-badge">{deviceTypeLabel(row.DeviceType)}</span>
                    {!campus && orgNameOf(row.OrganizationId) && <span className="device-type-badge dev-org-badge">{orgNameOf(row.OrganizationId)}</span>}
                  </div>
                  <span className={"dev-status " + (online ? "is-online" : "is-offline")}>
                    <i aria-hidden />{online ? "Online" : "Offline"}
                  </span>
                </header>

                <dl className="dev-facts">
                  <div><dt>IP address</dt><dd className="device-mono">{row.DeviceIPAddress || "—"}</dd></div>
                  <div><dt>Serial</dt><dd className="device-mono">{row.SerialNumber}</dd></div>
                  <div><dt>Punches</dt><dd>{directionLabel(row.DeviceDirection)}</dd></div>
                  <div><dt>Last seen</dt><dd title={formatIST(row.LastPing)}>{row.LastPing ? timeAgoIST(row.LastPing, true) : "Never"}</dd></div>
                </dl>

                <footer className="dev-actions">
                  {isCamera ? (
                    <button type="button" className="btn btn-primary-purple" onClick={() => navigate("/face")}>Monitor</button>
                  ) : (
                    <>
                      <button type="button" className={"btn " + (usersOpen ? "btn-primary-purple" : "btn-outline-reports")} onClick={() => showDeviceUsers(row.DeviceId)} disabled={usersOpen && usersMode === "read"}>Users</button>
                      <button type="button" className={"btn " + (detailsOpen ? "btn-primary-purple" : "btn-outline-reports")} onClick={() => toggleDetails(row)}>
                        {detailsOpen ? "Hide" : "Connectivity"}
                      </button>
                    </>
                  )}
                  <button type="button" className="btn btn-outline-reports" onClick={() => openEdit(row)}>Edit</button>
                  <button type="button" className="btn btn-outline-reports shift-delete" onClick={() => deleteDevice(row)}>Delete</button>
                </footer>
              </article>
            );
          })}
        </div>
      )}

      {/* ── Connectivity panel ── */}
      {detailRow && (
        <section className="section-card dev-panel">
          <div className="dev-panel-head">
            <div><p className="section-eyebrow">Connectivity</p><h3>{detailRow.DeviceName}</h3></div>
            <button type="button" className="btn btn-outline-reports" onClick={() => toggleDetails(detailRow)}>Close</button>
          </div>
          <div className="device-conn-grid">
            <div className="device-conn-facts">
              <dl>
                <div><dt>Endpoint</dt><dd className="device-mono">{detailRow.DeviceIPAddress || "—"}:4370 (SDK)</dd></div>
                <div><dt>Serial</dt><dd className="device-mono">{detailRow.SerialNumber}</dd></div>
                <div><dt>Type</dt><dd>{deviceTypeLabel(detailRow.DeviceType)}</dd></div>
                <div><dt>Last seen</dt><dd title={formatIST(detailRow.LastPing)}>{detailRow.LastPing ? timeAgoIST(detailRow.LastPing, true) : "Never"}</dd></div>
                <div><dt>Reachability</dt>
                  <dd>
                    {detail.testing ? "Testing…" : detail.testResult
                      ? <span className={detail.testOk ? "device-ok" : "device-err"}>{detail.testResult}</span>
                      : <span className="device-muted">Not tested yet</span>}
                  </dd>
                </div>
              </dl>
              <div className="device-conn-actions">
                <button type="button" className="btn btn-outline-reports" disabled={detail.testing} onClick={() => testDeviceInPanel(detailRow)}>
                  {detail.testing ? "Testing…" : "Test connection"}
                </button>
                <button type="button" className="btn btn-primary-purple" disabled={detail.fetching} onClick={() => fetchAttendance(detailRow)}>
                  {detail.fetching ? "Fetching…" : "Fetch punches now"}
                </button>
                <button type="button" className="btn btn-outline-reports" onClick={() => connectDevice(detailRow.DeviceId)}>Reconnect</button>
              </div>
              {detail.fetchResult && <p className="device-conn-note">{detail.fetchResult}</p>}
            </div>

            <div className="device-conn-log">
              <div className="device-conn-log-head">
                <h4>Recent activity</h4>
                <button type="button" className="device-linkbtn" onClick={() => loadCommLog(detailRow)}>Refresh</button>
              </div>
              {detail.commStatus && <p className="device-muted">{detail.commStatus}</p>}
              {detail.commLog.length > 0 && (
                <ul className="device-comm-list">
                  {detail.commLog.map((e: any, i: number) => (
                    <li key={i}>
                      <span className={`device-comm-tag ${String(e.action || "").toLowerCase().includes("push") || String(e.action || "").toLowerCase().includes("attlog") ? "push" : ""}`}>
                        {e.action || "—"}
                      </span>
                      <span className="device-comm-detail">{e.detail || ""}</span>
                      <span className="device-comm-time" title={formatIST(e.at)}>{e.at ? timeAgoIST(e.at, true) : ""}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </section>
      )}

      {/* ── Machine users panel ── */}
      {selectedDeviceId !== null && (
        <section className="section-card cfg-table-card dev-panel">
          <div className="cfg-toolbar">
            <div><p className="section-eyebrow" style={{ margin: 0 }}>Users on device</p><strong>{usersRow?.DeviceName || `Device ${selectedDeviceId}`}</strong></div>
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="btn btn-outline-reports" style={{ height: 36 }} onClick={() => refreshUsersFromDevice(selectedDeviceId)} disabled={usersMode !== ""}
                title="Ask the reader to re-send its users and templates (push channel)">{usersMode === "refresh" || usersMode === "reload" ? <><BtnSpinner />Refreshing…</> : "Refresh from device"}</button>
              <button type="button" className="btn btn-outline-reports" style={{ height: 36 }} disabled={usersMode !== "" || sendingNames}
                onClick={() => sendNames(selectedDeviceId)}
                title="Send the employee names saved on this server to the reader, so it shows them at punch time. Admin rights on the reader are kept.">
                {sendingNames ? <><BtnSpinner />Sending…</> : "Send names to device"}
              </button>
              <button type="button" className="btn btn-outline-reports" style={{ height: 36 }} onClick={closeUsers} disabled={usersMode === "read" || usersMode === "reload"}>Close</button>
            </div>
          </div>
          {readerStatus && readerStatus.last_poll_seconds !== null && (
            <p className={"dev-reader-poll " + (readerStatus.polling ? "is-ok" : "is-quiet")} role="status">
              <i aria-hidden />
              Reader last polled this server: <strong>{readerStatus.last_poll_text}</strong>
              {readerStatus.polling
                ? " · connected over Cloud/ADMS push"
                : " · not polling right now. Commands you send are queued and applied when it reconnects; if this stays, check its network and Cloud Server / ADMS setting."}
            </p>
          )}
          {usersMode === "read" && (
            <>
              <LoadingNote
                message={<>Reading users from {usersRow?.DeviceName || `device ${selectedDeviceId}`}…</>}
                hint="A reader on your network can take up to 30 seconds. A remote reader answers straight away from the last copy it sent to this server."
                bar
              />
              <SkeletonRows count={4} />
            </>
          )}
          {usersMode === "refresh" && (
            <LoadingNote
              message={<>Asked {usersRow?.DeviceName || `device ${selectedDeviceId}`} to send its users again…</>}
              hint={<>The reader answers over its next check-ins. The list is re-read every 10 s for up to 2 minutes
                ({reloadIn} s left){refreshCount !== null ? <> · <strong>{refreshCount}</strong> user(s) so far</> : null}.</>}
              bar
            />
          )}
          {usersMode === "reload" && <LoadingNote message="Updating the user list…" />}
          {usersMode === "" && usersStatus && (usersError ? (
            <p className="dev-users-status dev-users-error">
              <span>{usersStatus}</span>
              <button type="button" className="btn btn-outline-reports" style={{ height: 34 }} onClick={() => loadUsers(selectedDeviceId)}>Try again</button>
            </p>
          ) : <p className="dev-users-status">{usersStatus}</p>)}
          {usersMode === "" && deviceUsers.length > 0 && (() => {
            const t = templateTotals(deviceUsers);
            return (
              <div className="dev-users-summary">
                <strong>{t.users} {t.users === 1 ? "user" : "users"}</strong>
                <span>{t.withFace} with a face</span>
                <span>{t.withFinger} with a fingerprint{t.fingers > t.withFinger ? ` (${t.fingers} fingers in all)` : ""}</span>
                <span>{t.withPhoto} with a photo</span>
                <em>Counts are what this reader has sent to the server.</em>
                {!t.any && (
                  <p className="dev-users-hint">
                    No face or fingerprint data has been received from this reader yet.{" "}
                    <button type="button" className="device-linkbtn" onClick={() => navigate("/commands")}>Open Reader diagnostics</button>{" "}
                    to see what it sends.
                  </p>
                )}
              </div>
            );
          })()}
          {deviceUsers.length > 0 && (
            <table className="table cfg-table">
              <thead><tr><th>Code</th><th>Name</th><th>Role</th><th>Enabled</th><th>Face</th><th>Fingers</th><th>Photo</th><th /></tr></thead>
              <tbody>
                {deviceUsers.map((user) => (
                  <tr key={`${selectedDeviceId}-${user.EmployeeCode}`}>
                    <td>{user.EmployeeCode}</td>
                    <td>{user.EmployeeName || "—"}</td>
                    <td>{user.Role || "—"}</td>
                    <td>{user.Enabled === true ? <span className="badge badge-green">Yes</span> : user.Enabled === false ? <span className="badge badge-gray">No</span> : "—"}</td>
                    <TemplateCells user={user} />
                    <td className="cfg-actions">
                      <button type="button" className="btn btn-outline-reports"
                        onClick={() => fetchUserPhoto(selectedDeviceId, user.EmployeeCode)}
                        disabled={photoActionKey === `fetch-${selectedDeviceId}-${user.EmployeeCode}`}>
                        {photoActionKey === `fetch-${selectedDeviceId}-${user.EmployeeCode}` ? <><BtnSpinner />Fetching…</> : "Fetch photo"}
                      </button>
                      <button type="button" className="btn btn-outline-reports"
                        onClick={() => viewUserPhoto(user.EmployeeCode)}
                        disabled={photoActionKey === `view-${selectedDeviceId}-${user.EmployeeCode}`}>
                        {photoActionKey === `view-${selectedDeviceId}-${user.EmployeeCode}` ? <><BtnSpinner />Opening…</> : "View photo"}
                      </button>
                      <button type="button" className="btn btn-outline-reports shift-delete"
                        onClick={() => deleteDeviceUser(selectedDeviceId, user.EmployeeCode)}
                        disabled={deletingUserKey === `${selectedDeviceId}-${user.EmployeeCode}`}>
                        {deletingUserKey === `${selectedDeviceId}-${user.EmployeeCode}` ? <><BtnSpinner />Deleting…</> : "Delete"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {/* ── Photo preview ── */}
      {selectedPhoto && (
        <div className="modal-overlay" onClick={() => setSelectedPhoto(null)}>
          <div className="modal-dialog" style={{ maxWidth: 460 }} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Photo preview">
            <div className="emp-edit-card">
              <div className="emp-edit-head">
                <div><h3>Photo preview</h3><span className="emp-edit-sub">User {selectedPhoto.employeeCode} · Source: {selectedPhoto.source || "—"}</span></div>
                <button type="button" className="modal-close" onClick={() => setSelectedPhoto(null)} aria-label="Close">×</button>
              </div>
              <div style={{ padding: 24 }}>
                <img src={buildPhotoSrc(selectedPhoto.photoData, selectedPhoto.photoMimeType)} alt={`User ${selectedPhoto.employeeCode}`}
                  style={{ width: "100%", maxHeight: 360, objectFit: "contain", borderRadius: 14, background: "#fff", border: "1px solid var(--line)" }} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Add / edit popup ── */}
      {modal && (
        <ConfigModal
          title={modal === "add" ? "Add a device" : "Edit device"}
          subtitle={modal === "add" ? "Register a biometric reader or camera" : form.DeviceName}
          icon={Icons.devices}
          onClose={closeModal} onSubmit={submit} error={formError} saving={saving}
          submitLabel={modal === "add" ? "Add device" : "Save changes"}
        >
          <section className="emp-section">
            <SectionHead icon={Icons.devices} title="Device" desc="What it is and how it is identified" />
            <div className="emp-grid">
              <div className="field">
                <label htmlFor="dv-name">Device name <Req /></label>
                <input id="dv-name" value={form.DeviceName} placeholder="e.g. Main Entrance" onChange={(e) => setForm({ ...form, DeviceName: e.target.value })} />
              </div>
              {!campus && (
                <div className="field">
                  <label htmlFor="dv-org">Institution</label>
                  <select id="dv-org" value={form.OrganizationId} onChange={(e) => setForm({ ...form, OrganizationId: e.target.value })}>
                    <option value="">Not set (only Admin sees it)</option>
                    {organizations.map((o) => <option key={o.OrganizationId} value={String(o.OrganizationId)}>{o.OrgName}</option>)}
                  </select>
                  <span className="field-hint">Campus logins (User Roles) see only their institution's devices.</span>
                </div>
              )}
              <div className="field">
                <label htmlFor="dv-type">Device type</label>
                <select id="dv-type" value={form.DeviceType} onChange={(e) => setForm({ ...form, DeviceType: e.target.value })}>
                  {DEVICE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="dv-serial">Serial number {modal === "add" && <Req />}</label>
                <input id="dv-serial" value={form.SerialNumber} placeholder="On the device label or menu" disabled={modal === "edit"}
                  onChange={(e) => setForm({ ...form, SerialNumber: e.target.value })} />
                {modal === "edit" && <span className="field-hint">The serial number cannot be changed.</span>}
              </div>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.transfer} title="Network" desc="How the server reaches the device" />
            <div className="hours-row" style={{ marginBottom: 0 }}>
              <div style={{ flex: "1 1 220px", minWidth: 0 }}>
                <label className="field-label" htmlFor="dv-ip">IP address <Req /></label>
                <input id="dv-ip" style={{ width: "100%" }} value={form.DeviceIPAddress} placeholder="e.g. 192.168.1.205" inputMode="decimal"
                  onChange={(e) => setForm({ ...form, DeviceIPAddress: e.target.value })} />
              </div>
              <div>
                <label className="field-label" htmlFor="dv-port">SDK port</label>
                <input id="dv-port" type="number" min={1} max={65535} value={form.Port} onChange={(e) => setForm({ ...form, Port: e.target.value })} />
              </div>
              <div>
                <label className="field-label" htmlFor="dv-key">Comm Key</label>
                <input id="dv-key" type="number" min={0} max={999999} value={form.CommKey} placeholder="0 = none" style={{ width: 110 }}
                  title="The Comm Key set on the reader (Menu > Comm > Security > Comm Key). Needed for SDK features such as Fetch punches and Import users."
                  onChange={(e) => setForm({ ...form, CommKey: e.target.value })} />
              </div>
              <button type="button" className="btn btn-outline-reports" onClick={testSdkConnection}>Test connection</button>
            </div>
            {sdkStatus && (
              <div className={"en-status is-" + (sdkStatusOk === true ? "ok" : sdkStatusOk === false ? "err" : "info")} role="status">
                {sdkStatusOk === null && <span className="en-spinner" aria-hidden />}
                <span>{sdkStatus}</span>
              </div>
            )}
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.logs} title="Punch direction" desc="What a punch on this device means" />
            <Segmented label="Punch direction" value={form.DeviceDirection} onChange={(v) => setForm({ ...form, DeviceDirection: v })} options={DIRECTIONS} />
            <span className="field-hint" style={{ display: "block", marginTop: 8 }}>
              Use IN only for an entry reader and OUT only for an exit reader. IN / OUT is for a single reader that handles both.
            </span>
          </section>
        </ConfigModal>
      )}
    </div>
  );
}
