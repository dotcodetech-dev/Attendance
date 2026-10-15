import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api } from "../api/client";

/** Which optional modules are switched on in Module Configuration. */
export type Features = { student_attendance: boolean; student_leaves: boolean; mess_tokens: boolean };

/** Fired by Module Configuration after saving so the sidebar re-checks the switches. */
export const FEATURES_CHANGED_EVENT = "aveon:features-changed";

type FeaturesContextValue = { features: Features; loaded: boolean };

// Until the first answer arrives every module counts as off, so a menu never flashes and then vanishes.
const OFF: Features = { student_attendance: false, student_leaves: false, mess_tokens: false };
const FeaturesContext = createContext<FeaturesContextValue>({ features: OFF, loaded: false });

export function FeaturesProvider({ children }: { children: React.ReactNode }) {
  const [features, setFeatures] = useState<Features>(OFF);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(() => {
    api.getFeatures()
      .then((f: Features) => setFeatures({ student_attendance: !!f?.student_attendance, student_leaves: !!f?.student_leaves, mess_tokens: !!f?.mess_tokens }))
      .catch(() => setFeatures(OFF))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener(FEATURES_CHANGED_EVENT, refresh);
    return () => window.removeEventListener(FEATURES_CHANGED_EVENT, refresh);
  }, [refresh]);

  return <FeaturesContext.Provider value={{ features, loaded }}>{children}</FeaturesContext.Provider>;
}

export function useFeatures() {
  return useContext(FeaturesContext);
}
