import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api } from "../api/client";

export type Organization = {
  OrgName: string;
  OrgSubtitle: string;
  OrgAddress?: string | null;
  OrgPhone?: string | null;
  OrgEmail?: string | null;
  OrgLogo?: string | null;
};

const DEFAULT_ORG: Organization = { OrgName: "Aveon", OrgSubtitle: "FaceSync Admin" };

type OrgContextValue = { org: Organization; refresh: () => Promise<void> };

const OrgContext = createContext<OrgContextValue>({ org: DEFAULT_ORG, refresh: async () => {} });

export function OrgProvider({ children }: { children: React.ReactNode }) {
  const [org, setOrg] = useState<Organization>(DEFAULT_ORG);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getOrganization();
      if (data?.OrgName) setOrg(data);
    } catch {
      // keep defaults if unreachable
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return <OrgContext.Provider value={{ org, refresh }}>{children}</OrgContext.Provider>;
}

export function useOrg() {
  return useContext(OrgContext);
}
