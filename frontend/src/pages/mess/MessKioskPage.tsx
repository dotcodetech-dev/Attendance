import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { formatIST } from "../../utils/datetime";
import { printReceipt } from "../../utils/print";

// Full-screen mess kiosk: polls for newly issued tokens (from punches at the
// mess device) and, if auto-print is on, prints each one automatically.
export function MessKioskPage() {
  const [current, setCurrent] = useState<any | null>(null);
  const [count, setCount] = useState(0);
  const sinceId = useRef(0);
  const autoPrint = useRef(false);
  const queue = useRef<any[]>([]);
  const printing = useRef(false);
  // First poll only advances the feed pointer past today's backlog so a kiosk
  // (re)opened mid-day doesn't reprint every token already issued.
  const primed = useRef(false);

  const fmt = (iso?: string) => (iso ? formatIST(iso) : "");

  const printNext = () => {
    if (printing.current) return;
    const next = queue.current.shift();
    if (!next) return;
    printing.current = true;
    setCurrent(next);
    setCount((c) => c + 1);
    if (autoPrint.current) {
      window.setTimeout(() => {
        printReceipt();
        printing.current = false;
        window.setTimeout(printNext, 500);
      }, 300);
    } else {
      printing.current = false;
    }
  };

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res = await api.getMessKioskFeed(sinceId.current);
        autoPrint.current = !!res.auto_print;
        const toks = res.tokens || [];
        if (!primed.current) {
          primed.current = true;
          if (toks.length) {
            sinceId.current = Math.max(...toks.map((t: any) => t.MessTokenId));
            setCurrent(toks[toks.length - 1]); // show latest for reference, no print
          }
        } else if (toks.length) {
          sinceId.current = Math.max(...toks.map((t: any) => t.MessTokenId));
          queue.current.push(...toks);
          if (!current) setCurrent(toks[0]);
          printNext();
        }
      } catch {
        // ignore
      }
      if (alive) window.setTimeout(poll, 3000);
    };
    poll();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const org = current?.organization || {};

  return (
    <div style={{ minHeight: "80vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16 }}>
      <div className="no-print" style={{ textAlign: "center" }}>
        <h2 style={{ margin: 0 }}>Mess Kiosk</h2>
        <p className="sub">Waiting for punches at the mess device… tokens print automatically. Keep this page open on the counter PC.</p>
        <span className="badge badge-blue">{count} printed this session</span>
      </div>

      {current ? (
        <div className="mess-receipt" id="mess-receipt">
          <div className="mr-org">{org.OrgName || "Aveon"}</div>
          {org.OrgAddress ? <div className="mr-addr">{org.OrgAddress}</div> : null}
          <div className="mr-title">MESS TOKEN</div>
          <div className="mr-hr" />
          <div className="mr-meal">{current.MealType}</div>
          <div className="mr-tokenno">{current.TokenLabel}</div>
          <div className="mr-hr" />
          <div className="mr-row"><span>Name</span><b>{current.EmployeeName || "-"}</b></div>
          <div className="mr-row"><span>ID</span><b>{current.EmployeeCode}</b></div>
          <div className="mr-row"><span>Date</span><b>{current.TokenDate}</b></div>
          <div className="mr-row"><span>Time</span><b>{fmt(current.CreatedAt)}</b></div>
          {current.qr ? <img className="mr-qr" src={current.qr} alt="token qr" /> : null}
          <div className="mr-hr" />
          <div className="mr-valid">Valid for One-Time Meal Only</div>
        </div>
      ) : (
        <div className="empty-state no-print">No tokens yet.</div>
      )}

      {current && <button className="no-print btn btn-outline-reports" onClick={() => printReceipt()}>Print again</button>}
    </div>
  );
}
