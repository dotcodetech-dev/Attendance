import { FormEvent, useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { formatIST } from "../../utils/datetime";
import { printReceipt } from "../../utils/print";

export function MessTokenPage() {
  const [employeeCode, setEmployeeCode] = useState("");
  const [token, setToken] = useState<any | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getMessSettings().then((s) => setEnabled(s.enabled)).catch(() => setEnabled(null));
    inputRef.current?.focus();
  }, []);

  const generate = async (e: FormEvent) => {
    e.preventDefault();
    if (!employeeCode.trim()) return;
    setBusy(true);
    setMessage("");
    setToken(null);
    try {
      const res = await api.generateMessToken(employeeCode.trim());
      if (!res.ok) {
        setMessage(res.message || "Could not generate token.");
      } else {
        setToken(res);
        setMessage(res.already_generated ? res.message : "");
      }
    } catch (err: any) {
      setMessage(err?.message || "Failed to generate token.");
    } finally {
      setBusy(false);
    }
  };

  const reprint = async () => {
    if (!token) return;
    try {
      const res = await api.reprintMessToken(token.MessTokenId);
      setToken({ ...token, ...res });
      window.setTimeout(() => printReceipt(), 100);
    } catch (err: any) {
      setMessage(err?.message || "Reprint failed.");
    }
  };

  const printNow = () => printReceipt();

  const reset = () => {
    setToken(null); setMessage(""); setEmployeeCode("");
    inputRef.current?.focus();
  };

  const org = token?.organization || {};
  const fmt = (iso?: string) => (iso ? formatIST(iso) : "");

  return (
    <div>
      <div className="page-head no-print">
        <div>
          <h2>Mess Token</h2>
          <p className="sub">Enter an employee code to issue a meal token for the current meal window.</p>
        </div>
        {enabled === false && <span className="badge badge-red">Mess token printing is disabled in Settings</span>}
      </div>

      <form className="toolbar no-print" onSubmit={generate}>
        <div className="field"><label>Employee Code</label>
          <input ref={inputRef} value={employeeCode} onChange={(e) => setEmployeeCode(e.target.value)} placeholder="Scan or type ID" autoFocus />
        </div>
        <div className="toolbar-actions">
          <button type="submit" className="btn btn-primary-purple" disabled={busy || enabled === false}>{busy ? "…" : "Print Token"}</button>
          {token && <button type="button" className="btn btn-outline-reports" onClick={reset}>New</button>}
        </div>
      </form>

      {message && <p className={"no-print " + (message.includes("already") ? "note-err" : "note-err")}>{message}</p>}

      {token && (
        <>
          <div className="mess-receipt" id="mess-receipt">
            <div className="mr-org">{org.OrgName || "Aveon"}</div>
            {org.OrgAddress ? <div className="mr-addr">{org.OrgAddress}</div> : null}
            <div className="mr-title">MESS TOKEN</div>
            <div className="mr-hr" />
            <div className="mr-meal">{token.MealType}</div>
            <div className="mr-tokenno">{token.TokenLabel}</div>
            <div className="mr-hr" />
            <div className="mr-row"><span>Name</span><b>{token.EmployeeName || "-"}</b></div>
            <div className="mr-row"><span>ID</span><b>{token.EmployeeCode}</b></div>
            <div className="mr-row"><span>Date</span><b>{token.TokenDate}</b></div>
            <div className="mr-row"><span>Time</span><b>{fmt(token.CreatedAt)}</b></div>
            {token.ReprintCount > 0 ? <div className="mr-row"><span>Reprint</span><b>#{token.ReprintCount}</b></div> : null}
            {token.qr ? <img className="mr-qr" src={token.qr} alt="token qr" /> : null}
            <div className="mr-hr" />
            <div className="mr-valid">Valid for One-Time Meal Only</div>
          </div>

          <div className="no-print" style={{ marginTop: 14, display: "flex", gap: 10 }}>
            <button className="btn btn-primary-purple" onClick={printNow}>Print</button>
            <button className="btn btn-outline-reports" onClick={reprint}>Reprint (log it)</button>
          </div>
        </>
      )}
    </div>
  );
}
