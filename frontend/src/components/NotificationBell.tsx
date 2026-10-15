import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Icons } from "./SidebarIcons";
import { api } from "../api/client";

type Note = {
  id: string;
  kind: "device" | "leave" | "manual" | "student";
  severity: "critical" | "warning" | "info";
  title: string;
  message: string;
  link: string;
  time: string | null;
};

const SEEN_KEY = "aveon:notif-seen";
const REFRESH_MS = 60_000;

// "Seen" ids live in this browser only. An id carries the count (e.g. "leaves:3"), so a change re-notifies.
const readSeen = (): string[] => {
  try { return JSON.parse(localStorage.getItem(SEEN_KEY) || "[]"); } catch { return []; }
};
const writeSeen = (ids: string[]) => {
  try { localStorage.setItem(SEEN_KEY, JSON.stringify(ids)); } catch { /* storage blocked: badge just won't persist */ }
};

function ago(iso: string | null): string {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h} hr ago`;
  return `${Math.round(h / 24)} d ago`;
}

const KIND_ICON: Record<Note["kind"], React.ReactNode> = {
  device: Icons.devices,
  leave: Icons.leaves,
  manual: Icons.edit,
  student: Icons.employees,
};

export function NotificationBell() {
  const navigate = useNavigate();
  const [notes, setNotes] = useState<Note[]>([]);
  const [seen, setSeen] = useState<string[]>(readSeen);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    api.getNotifications()
      .then((r: any) => { setNotes(r?.items ?? []); setFailed(false); })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    load();
    const t = window.setInterval(load, REFRESH_MS);
    window.addEventListener("focus", load);
    return () => { window.clearInterval(t); window.removeEventListener("focus", load); };
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const unseen = notes.filter((n) => !seen.includes(n.id)).length;

  const markAllRead = () => {
    const ids = notes.map((n) => n.id);
    setSeen(ids);
    writeSeen(ids);
  };

  const go = (n: Note) => {
    setSeen((s) => { const next = Array.from(new Set([...s, n.id])); writeSeen(next); return next; });
    setOpen(false);
    navigate(n.link);
  };

  return (
    <div className="notif-wrap" ref={wrapRef}>
      <button type="button" className="topbar-icon-btn" aria-label={unseen ? `Notifications, ${unseen} new` : "Notifications"}
        aria-expanded={open} aria-haspopup="true" onClick={() => { setOpen((o) => !o); if (!open) load(); }}>
        <span className="topbar-bell">{Icons.bell}</span>
        {unseen > 0 && <span className="topbar-badge" aria-hidden>{unseen > 9 ? "9+" : unseen}</span>}
      </button>

      {open && (
        <div className="notif-panel" role="dialog" aria-label="Notifications">
          <div className="notif-head">
            <strong>Notifications</strong>
            <button type="button" className="notif-link" onClick={markAllRead} disabled={unseen === 0}>Mark all as read</button>
          </div>
          {failed && <p className="notif-empty">Could not load notifications. Check the connection.</p>}
          {!failed && notes.length === 0 && (
            <div className="notif-empty">
              <span className="notif-empty-icon" aria-hidden>✓</span>
              <strong>You're all caught up</strong>
              <span>Nothing needs your attention right now.</span>
            </div>
          )}
          <ul className="notif-list">
            {notes.map((n) => (
              <li key={n.id}>
                <button type="button" className={"notif-item" + (seen.includes(n.id) ? "" : " is-new")} onClick={() => go(n)}>
                  <span className={"notif-icon sev-" + n.severity} aria-hidden>{KIND_ICON[n.kind]}</span>
                  <span className="notif-body">
                    <span className="notif-title">{n.title}</span>
                    <span className="notif-msg">{n.message}</span>
                    {n.time && <span className="notif-time">{ago(n.time)}</span>}
                  </span>
                  {!seen.includes(n.id) && <span className="notif-dot" aria-label="New" />}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
