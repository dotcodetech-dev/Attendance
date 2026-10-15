import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { Icons } from "../components/SidebarIcons";
import { Req } from "../components/Req";
import { SectionHead } from "../components/ConfigUi";
import { useOrg } from "../store/org";

type OrgForm = {
  OrgName: string;
  OrgSubtitle: string;
  OrgAddress: string;
  OrgPhone: string;
  OrgEmail: string;
  OrgLogo: string;
};

const blank: OrgForm = { OrgName: "", OrgSubtitle: "", OrgAddress: "", OrgPhone: "", OrgEmail: "", OrgLogo: "" };

export function OrganizationConfigPage() {
  const { refresh } = useOrg();
  const [form, setForm] = useState<OrgForm>(blank);
  const [status, setStatus] = useState<{ text: string; ok: boolean } | null>(null);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getOrganization()
      .then((d) => setForm({
        OrgName: d.OrgName || "", OrgSubtitle: d.OrgSubtitle || "", OrgAddress: d.OrgAddress || "",
        OrgPhone: d.OrgPhone || "", OrgEmail: d.OrgEmail || "", OrgLogo: d.OrgLogo || "",
      }))
      .catch(() => setStatus({ text: "Failed to load current settings.", ok: false }));
  }, []);

  const set = (k: keyof OrgForm, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const onLogo = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 512 * 1024) { setStatus({ text: "The logo must be under 512 KB.", ok: false }); return; }
    const reader = new FileReader();
    reader.onload = () => { set("OrgLogo", String(reader.result || "")); setStatus(null); };
    reader.readAsDataURL(file); // base64 data URL
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.OrgName.trim()) { setStatus({ text: "Enter the organization name.", ok: false }); return; }
    setSaving(true); setStatus(null);
    try {
      await api.updateOrganization({ ...form });
      await refresh(); // update the sidebar immediately
      setStatus({ text: "Organization settings saved.", ok: true });
    } catch (err: any) {
      setStatus({ text: err?.message || "Failed to save.", ok: false });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>Organization Settings</h2>
          <p className="sub">Your name and logo appear in the sidebar. The address, phone and email print on report PDFs.</p>
        </div>
      </div>

      <div className="org-layout">
        <form onSubmit={submit} className="org-form">
          <section className="emp-section">
            <SectionHead icon={Icons.document} title="Identity" desc="How your organization is named in the app" />
            <div className="emp-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
              <div className="field">
                <label htmlFor="org-name">Organization name <Req /></label>
                <input id="org-name" value={form.OrgName} onChange={(e) => set("OrgName", e.target.value)} required />
              </div>
              <div className="field">
                <label htmlFor="org-sub">Tagline</label>
                <input id="org-sub" value={form.OrgSubtitle} onChange={(e) => set("OrgSubtitle", e.target.value)} placeholder="e.g. Attendance System" />
              </div>
            </div>
            <div style={{ marginTop: 22 }}>
              <span className="field-label">Logo</span>
              <div className="org-logo-row">
                <span className="org-logo-box">
                  {form.OrgLogo ? <img src={form.OrgLogo} alt="Logo preview" /> : <span aria-hidden>{(form.OrgName || "A").charAt(0).toUpperCase()}</span>}
                </span>
                <div>
                  <input ref={fileRef} type="file" accept="image/*" hidden onChange={onLogo} />
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button type="button" className="btn btn-outline-reports" onClick={() => fileRef.current?.click()}>{form.OrgLogo ? "Change logo" : "Upload logo"}</button>
                    {form.OrgLogo && <button type="button" className="btn btn-outline-reports shift-delete" onClick={() => set("OrgLogo", "")}>Remove</button>}
                  </div>
                  <span className="field-hint">PNG, JPG or SVG, under 512 KB. A square image works best.</span>
                </div>
              </div>
            </div>
          </section>

          <section className="emp-section">
            <SectionHead icon={Icons.bell} title="Contact details" desc="Printed in the header of reports" />
            <div className="emp-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
              <div className="field field-full">
                <label htmlFor="org-addr">Address</label>
                <textarea id="org-addr" value={form.OrgAddress} onChange={(e) => set("OrgAddress", e.target.value)} rows={3} placeholder="Street, city, PIN" />
              </div>
              <div className="field">
                <label htmlFor="org-phone">Phone</label>
                <input id="org-phone" type="tel" value={form.OrgPhone} onChange={(e) => set("OrgPhone", e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="org-email">Email</label>
                <input id="org-email" type="email" value={form.OrgEmail} onChange={(e) => set("OrgEmail", e.target.value)} />
              </div>
            </div>
          </section>

          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            <button type="submit" className="btn btn-primary-purple" disabled={saving}>{saving ? "Saving…" : "Save organization"}</button>
            {status && <span className={status.ok ? "note-ok" : "note-err"} style={{ margin: 0, fontWeight: 600 }} role="status">{status.text}</span>}
          </div>
        </form>

        <aside className="org-preview" aria-label="Sidebar preview">
          <p className="section-eyebrow">Sidebar preview</p>
          <div className="org-brand">
            <span className="org-brand-icon">
              {form.OrgLogo ? <img src={form.OrgLogo} alt="" /> : <span aria-hidden>{(form.OrgName || "A").charAt(0).toUpperCase()}</span>}
            </span>
            <div>
              <strong>{form.OrgName || "Organization name"}</strong>
              <span>{form.OrgSubtitle || "Tagline"}</span>
            </div>
          </div>
          <p className="org-preview-note">This is how the top of the sidebar will look after you save.</p>
        </aside>
      </div>
    </div>
  );
}
