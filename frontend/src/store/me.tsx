import { createContext, useContext, useEffect, useState } from "react";

import { api } from "../api/client";

/** The signed-in login. `campus` is set for a campus role (User Roles): one institution and its menu switches. */
export type Me = {
  login: string | null;
  role: string | null;
  campus: null | {
    role: string;
    organization_id: number | null;
    organization_name: string | null;
    permissions: Record<string, boolean>;
  };
};

type MeContextValue = { me: Me | null; loaded: boolean; can: (perm?: string) => boolean };

// Until /auth/me answers, nothing is hidden for a full login and nothing is shown for a campus one.
const MeContext = createContext<MeContextValue>({ me: null, loaded: false, can: () => true });

export function MeProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.getMe().then(setMe).catch(() => setMe(null)).finally(() => setLoaded(true));
  }, []);

  // Admin, Manager, Employee: menus as today. A campus role: only the menus its switches allow.
  const can = (perm?: string) => {
    if (!perm || !me?.campus) return true;
    return !!me.campus.permissions[perm];
  };

  return <MeContext.Provider value={{ me, loaded, can }}>{children}</MeContext.Provider>;
}

export function useMe() {
  return useContext(MeContext);
}

/** The institution a campus login is limited to, or null for everyone else. */
export function useCampusOrg(): { id: number; name: string } | null {
  const { me } = useMe();
  const c = me?.campus;
  return c && c.organization_id ? { id: c.organization_id, name: c.organization_name || "Your institution" } : null;
}
