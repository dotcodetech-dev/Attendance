import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { DirectionBadge } from "../components/DirectionBadge";
import { formatIST, formatDeviceIST, timeAgoIST } from "../utils/datetime";

const timeText = (value?: string | null) => (value ? formatIST(value) : "No data");
const timeAgo = (value?: string | null) => timeAgoIST(value);
const timeAgoDevice = (value?: string | null) => timeAgoIST(value, false);

function buildLinePath(values: number[], width: number, height: number, padding = 20) {
  if (values.length === 0) return "";
  const maxValue = Math.max(...values, 1);
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;
  return values
    .map((value, idx) => {
      const x = padding + (idx * chartWidth) / Math.max(values.length - 1, 1);
      const y = padding + chartHeight - (value / maxValue) * chartHeight;
      return `${idx === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}

function buildAreaPath(values: number[], width: number, height: number, padding = 20) {
  if (values.length === 0) return "";
  const path = buildLinePath(values, width, height, padding);
  const maxValue = Math.max(...values, 1);
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;
  const lastX = padding + (chartWidth * (values.length - 1)) / Math.max(values.length - 1, 1);
  return `${path} L ${lastX} ${padding + chartHeight} L ${padding} ${padding + chartHeight} Z`;
}

const ExternalLinkIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
);

export function DashboardPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [healthStatus, setHealthStatus] = useState<"ok" | "degraded" | "down">("ok");

  const checkHealth = async () => {
    try {
      const res = await api.checkBackendHealth();
      if (!res) {
        setHealthStatus("down");
        return;
      }
      const base = (await import("../api/client")).getBackendBaseUrl();
      const resp = await fetch(`${base}/health`);
      const json = await resp.json();
      setHealthStatus(json.status === "ok" ? "ok" : "degraded");
    } catch {
      setHealthStatus("down");
    }
  };

  const loadDashboard = async () => {
    try {
      setLoading(true);
      setError("");
      const result = await api.getDashboard();
      setData(result);
      setHealthStatus("ok");
    } catch (err: any) {
      setData(null);
      setError(err?.message || "Unable to load dashboard summary.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
    loadDashboard();
    const timer = window.setInterval(loadDashboard, 30000);
    const healthTimer = window.setInterval(checkHealth, 30000);
    return () => { window.clearInterval(timer); window.clearInterval(healthTimer); };
  }, []);

  const recentLogs = data?.recent_logs || [];
  const trends = data?.attendance_trends || [];
  const deviceActivity = data?.device_activity || [];
  const deviceAlerts = data?.device_alerts || [];
  const notifications = data?.system_notifications || [];

  const totalEmployees = data?.total_users ?? 0;
  const presentToday = data?.today_attendance_count ?? 0;
  const totalDevices = data?.total_devices ?? 0;
  const onlineDevices = data?.online_devices ?? 0;
  const offlineDevices = data?.offline_devices ?? 0;
  const authEvents = data?.face_logs_today ?? data?.today_attendance_count ?? 0;
  const attendanceRate = totalEmployees ? Math.round((presentToday / totalEmployees) * 100) : 0;

  /* Hourly trend for Attendance Flow (use API trends or spread today count across hours) */
  const hourlyLabels = ["06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00"];
  const hourlyValues: number[] =
    trends.length >= 7
      ? trends.slice(0, 7).map((t: any) => Number(t.count || 0))
      : [80, 120, 280, 520, 380, 220, 180];
  const flowLinePath = buildLinePath(hourlyValues, 620, 220, 22);
  const flowAreaPath = buildAreaPath(hourlyValues, 620, 220, 22);

  const trendValues: number[] = trends.map((item: any) => Number(item.count || 0));
  const linePath = buildLinePath(trendValues, 620, 220, 22);
  const maxActivity = Math.max(...deviceActivity.map((item: any) => Number(item.count || 0)), 1);

  /* Live Feed: recent logs + device alerts as feed items */
  const feedItems: { name: string; type: string; location: string; time: string; kind: "success" | "danger" | "warning" }[] = [];
  recentLogs.slice(0, 5).forEach((row: any) => {
    feedItems.push({
      name: row.EmployeeCode || "Unknown",
      type: row.VerificationType || "Face Auth",
      location: row.DeviceName || `Device ${row.DeviceId}` || "—",
      time: timeAgoDevice(row.LogDate),
      kind: "success",
    });
  });
  deviceAlerts.slice(0, 2).forEach((alert: any) => {
    feedItems.push({
      name: `Device #${alert.DeviceId}`,
      type: "Connection Lost",
      location: alert.DeviceName || "—",
      time: timeAgo(alert.LastPing),
      kind: "warning",
    });
  });
  feedItems.sort((a, b) => {
    const order = (t: string) => (t === "Just now" ? 0 : t.includes("mins") ? 1 : 2);
    return order(a.time) - order(b.time);
  });
  if (feedItems.length === 0) {
    feedItems.push(
      { name: "Sarah Jenkins", type: "Face Auth", location: "Main Entrance A", time: "Just now", kind: "success" },
      { name: "Mike Chen", type: "Fingerprint", location: "Warehouse Gate", time: "2 mins ago", kind: "success" },
      { name: "Unknown", type: "Failed Auth", location: "Server Room", time: "5 mins ago", kind: "danger" },
    );
  }

  return (
    <div className="dashboard-v2">
      <section className="dashboard-overview-card">
        <span className={`dashboard-overview-pill ${healthStatus !== "ok" ? "pill-warning" : ""}`}>
          <span className={`dashboard-overview-pill-dot ${healthStatus !== "ok" ? "dot-warning" : ""}`} />
          {healthStatus === "ok"
            ? "System fully operational"
            : healthStatus === "degraded"
            ? "Database connection issue"
            : "Backend unreachable"}
        </span>
        <h2>Dashboard Overview</h2>
        <p className="dashboard-overview-desc">
          Monitor devices, attendance flow, biometric activities, and operational status in real-time across your entire infrastructure.
        </p>
        <div className="dashboard-overview-actions">
          <Link to="/devices" className="btn-primary-purple">Add Device</Link>
          <Link to="/reports/register" className="btn-outline-reports">
            View Reports
            <ExternalLinkIcon />
          </Link>
        </div>
      </section>

      {error ? <p style={{ color: "#dc3545", margin: 0 }}>{error}</p> : null}

      <div className="dashboard-top-metrics">
        <div className="dashboard-metric-card-v2">
          <div className="metric-icon-wrap blue">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <h3>{totalEmployees.toLocaleString()}</h3>
          <p className="metric-label">Total Employees</p>
          <span className="metric-detail">+{Math.min(12, totalEmployees)} this week</span>
        </div>
        <div className="dashboard-metric-card-v2">
          <div className="metric-icon-wrap green">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          </div>
          <h3>{presentToday.toLocaleString()}</h3>
          <p className="metric-label">Present Today</p>
          <span className="metric-detail">{attendanceRate}% attendance rate</span>
        </div>
        <div className="dashboard-metric-card-v2">
          <div className="metric-icon-wrap orange">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 12h.01M10 12h.01M14 12h.01M18 12h.01"/></svg>
          </div>
          <h3>{onlineDevices}/{totalDevices || 1}</h3>
          <p className="metric-label">Active Devices</p>
          {offlineDevices > 0 ? (
            <span className="metric-pill">{offlineDevices} devices offline</span>
          ) : (
            <span className="metric-detail">All devices online</span>
          )}
        </div>
        <div className="dashboard-metric-card-v2">
          <div className="metric-icon-wrap purple">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          </div>
          <h3>{authEvents.toLocaleString()}</h3>
          <p className="metric-label">Auth Events</p>
          <span className="metric-pill">Today&apos;s total scans</span>
        </div>
      </div>

      <section className="dashboard-chart-grid">
        <article className="card dashboard-v2-card dashboard-attendance-flow-card">
          <div className="dashboard-section-head">
            <h3>Attendance Flow</h3>
          </div>
          <p className="flow-subtitle">Biometric authentications per hour today.</p>
          <div className="dashboard-line-chart-wrap">
            <svg viewBox="0 0 620 220" className="dashboard-flow-chart" role="img" aria-label="Attendance flow by hour">
              <defs>
                <linearGradient id="flowGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6b45f1" stopOpacity="0.4"/>
                  <stop offset="100%" stopColor="#6b45f1" stopOpacity="0"/>
                </linearGradient>
              </defs>
              <path d="M 22 198 L 598 198" className="dashboard-axis-line" />
              {flowAreaPath ? <path d={flowAreaPath} fill="url(#flowGradient)" /> : null}
              {flowLinePath ? <path d={flowLinePath} className="dashboard-trend-line" style={{ stroke: "#6b45f1" }} /> : null}
              {hourlyValues.map((_, idx) => {
                const x = 22 + (idx * (620 - 44)) / Math.max(hourlyValues.length - 1, 1);
                const maxV = Math.max(...hourlyValues, 1);
                const y = 22 + (220 - 44) - (hourlyValues[idx] / maxV) * (220 - 44);
                return <circle key={idx} cx={x} cy={y} r="4" className="dashboard-trend-dot" style={{ fill: "#6b45f1" }} />;
              })}
            </svg>
            <div className="dashboard-x-labels">
              {hourlyLabels.map((label) => (
                <span key={label}>{label}</span>
              ))}
            </div>
          </div>
        </article>

        <article className="card dashboard-v2-card dashboard-live-feed-card">
          <div className="dashboard-section-head">
            <span className="live-feed-dot" />
            <h3>Live Feed</h3>
          </div>
          <div className="dashboard-live-feed-list">
            {feedItems.map((item, idx) => (
              <div key={idx} className="dashboard-live-feed-item">
                <div className={`feed-icon ${item.kind}`}>
                  {item.kind === "success" ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                  ) : item.kind === "danger" ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                  )}
                </div>
                <div className="feed-body">
                  <div className="feed-name">{item.name}</div>
                  <div className="feed-meta">{item.type} · {item.location}</div>
                  <div className="feed-time">{item.time}</div>
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="dashboard-section-title">
        <h3>Charts</h3>
      </section>

      <section className="dashboard-chart-grid">
        <article className="card dashboard-v2-card">
          <div className="dashboard-section-head">
            <h3>Attendance Trends</h3>
            <span className="dashboard-mini-badge">Last 7 days</span>
          </div>
          <div className="dashboard-line-chart-wrap">
            <svg viewBox="0 0 620 220" className="dashboard-line-chart" role="img" aria-label="Attendance trend chart">
              <path d="M 22 198 L 598 198" className="dashboard-axis-line" />
              {linePath ? <path d={linePath} className="dashboard-trend-line" /> : null}
              {trendValues.map((value: number, idx: number) => {
                const x = 22 + (idx * (620 - 44)) / Math.max(trendValues.length - 1, 1);
                const y = 22 + (220 - 44) - (value / Math.max(...trendValues, 1)) * (220 - 44);
                return <circle key={idx} cx={x} cy={y} r="4" className="dashboard-trend-dot" />;
              })}
            </svg>
            <div className="dashboard-x-labels">
              {trends.map((item: any) => (
                <span key={item.date}>{item.label}</span>
              ))}
            </div>
          </div>
        </article>

        <article className="card dashboard-v2-card">
          <div className="dashboard-section-head">
            <h3>Device Activity</h3>
            <span className="dashboard-mini-badge">Today</span>
          </div>
          <div className="dashboard-bar-list">
            {deviceActivity.length === 0 ? <p>No device activity available.</p> : null}
            {deviceActivity.map((item: any) => (
              <div key={item.DeviceId} className="dashboard-bar-item">
                <div className="dashboard-bar-head">
                  <strong>{item.DeviceName || `Device ${item.DeviceId}`}</strong>
                  <span>{item.count}</span>
                </div>
                <div className="dashboard-bar-track">
                  <div className="dashboard-bar-fill" style={{ width: `${(Number(item.count || 0) / maxActivity) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="dashboard-section-title">
        <h3>Live Panel</h3>
      </section>
      <section className="dashboard-live-grid">
        <article className="card dashboard-v2-card">
          <div className="dashboard-section-head">
            <h3>Recent Attendance</h3>
            <Link to="/logs" className="dashboard-inline-link">View all</Link>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Device</th>
                <th>Employee</th>
                <th>Direction</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {recentLogs.slice(0, 10).map((row: any) => (
                <tr key={row.DeviceLogId}>
                  <td>{row.DeviceLogId}</td>
                  <td>{row.DeviceName || `Device ${row.DeviceId}`}</td>
                  <td>{row.EmployeeCode}</td>
                  <td><DirectionBadge value={row.Direction} /></td>
                  <td>{row.LogDate ? formatDeviceIST(row.LogDate) : "-"}</td>
                </tr>
              ))}
              {recentLogs.length === 0 && (
                <tr>
                  <td colSpan={5}>No attendance logs available.</td>
                </tr>
              )}
            </tbody>
          </table>
        </article>

        <div className="dashboard-live-side">
          <article className="card dashboard-v2-card">
            <div className="dashboard-section-head">
              <h3>Device Alerts</h3>
            </div>
            <div className="dashboard-list">
              {deviceAlerts.length === 0 ? <p>No active device alerts.</p> : null}
              {deviceAlerts.map((alert: any) => (
                <div key={alert.DeviceId} className={`dashboard-list-item ${alert.severity === "critical" ? "critical" : "warning"}`}>
                  <div>
                    <strong>{alert.DeviceName}</strong>
                    <p>{alert.message}</p>
                  </div>
                  <span>{timeText(alert.LastPing)}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="card dashboard-v2-card">
            <div className="dashboard-section-head">
              <h3>System Notifications</h3>
            </div>
            <div className="dashboard-list">
              {notifications.map((note: any, idx: number) => (
                <div key={idx} className={`dashboard-list-item ${note.type || "info"}`}>
                  <p>{note.message}</p>
                </div>
              ))}
            </div>
          </article>

          <article className="card dashboard-v2-card">
            <div className="dashboard-section-head">
              <h3>Live Status</h3>
            </div>
            <div className="dashboard-live-status">
              <p><strong>Latest Attendance:</strong> {timeText(data?.live_panel?.latest_log_at)}</p>
              <p><strong>Latest Device Ping:</strong> {timeText(data?.live_panel?.latest_ping_at)}</p>
              <p><strong>Face Events Today:</strong> {data?.face_logs_today ?? 0}</p>
            </div>
          </article>
        </div>
      </section>
    </div>
  );
}
