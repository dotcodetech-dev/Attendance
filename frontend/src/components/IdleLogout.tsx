import { useEffect, useRef, useState } from "react";

/** Signed out after this long with no mouse, keyboard, touch or scroll activity. */
export const IDLE_LOGOUT_MS = 5 * 60 * 1000;
/** A warning with a countdown appears this long before the sign-out. */
const WARN_BEFORE_MS = 60 * 1000;
// Shared by every open tab, so working in one tab keeps the others signed in too.
const LAST_ACTIVITY_KEY = "last_activity_at";
const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "touchstart", "wheel", "scroll"] as const;

function readShared(): number {
  try { return Number(localStorage.getItem(LAST_ACTIVITY_KEY)) || 0; } catch { return 0; }
}
function writeShared(t: number) {
  try { localStorage.setItem(LAST_ACTIVITY_KEY, String(t)); } catch { /* private mode: this tab still works */ }
}

/**
 * Auto logout after 5 minutes on standby. Mounted inside the signed-in layout only. A minute before, a dialog
 * counts down with "Stay signed in"; any activity also resets the timer. `onTimeout` signs the user out.
 */
export function IdleLogout({ onTimeout }: { onTimeout: () => void }) {
  const last = useRef(Date.now());
  const [left, setLeft] = useState<number | null>(null);   // ms until sign-out while the warning shows
  const fired = useRef(false);

  useEffect(() => {
    last.current = Date.now();
    writeShared(last.current);
    let lastWrite = last.current;
    const bump = () => {
      const now = Date.now();
      last.current = now;
      if (now - lastWrite > 5000) { writeShared(now); lastWrite = now; }   // throttled: mousemove fires a lot
    };
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, bump, { passive: true }));
    const tick = window.setInterval(() => {
      const idle = Date.now() - Math.max(last.current, readShared());
      const remaining = IDLE_LOGOUT_MS - idle;
      if (remaining <= 0) {
        if (!fired.current) { fired.current = true; onTimeout(); }
      } else {
        setLeft(remaining <= WARN_BEFORE_MS ? remaining : null);
      }
    }, 1000);
    return () => {
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, bump));
      window.clearInterval(tick);
    };
  }, [onTimeout]);

  if (left == null) return null;
  const secs = Math.ceil(left / 1000);
  const stay = () => { last.current = Date.now(); writeShared(last.current); setLeft(null); };
  return (
    <div className="modal-overlay idle-overlay" role="presentation">
      <div className="modal-dialog idle-dialog" role="alertdialog" aria-modal="true" aria-labelledby="idle-title" aria-describedby="idle-text">
        <h3 id="idle-title">Still there?</h3>
        <p id="idle-text">
          You will be signed out in <b>{secs} second{secs === 1 ? "" : "s"}</b> because there was no activity for a while.
        </p>
        <div className="idle-actions">
          <button type="button" className="btn btn-outline-reports" onClick={onTimeout}>Sign out now</button>
          <button type="button" className="btn btn-primary-purple" onClick={stay} autoFocus>Stay signed in</button>
        </div>
      </div>
    </div>
  );
}
