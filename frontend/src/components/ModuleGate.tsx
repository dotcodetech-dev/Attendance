import { Link } from "react-router-dom";

import { Features, useFeatures } from "../store/features";

const LABEL: Record<keyof Features, string> = {
  student_attendance: "Student Attendance",
  student_leaves: "Student Leaves",
  mess_tokens: "Mess Token Printing",
};

/** Shows the page only while its module is switched on; otherwise explains how to turn it on. */
export function ModuleGate({ feature, children }: { feature: keyof Features; children: JSX.Element }) {
  const { features, loaded } = useFeatures();
  if (!loaded) return <div className="section-card"><p style={{ margin: 0 }}>Loading…</p></div>;
  if (features[feature]) return children;
  return (
    <div className="section-card sd-empty" role="status">
      <h3>{LABEL[feature]} is turned off</h3>
      <p>Switch it on in Module Configuration and its menu and pages will appear.</p>
      <Link to="/config/mess" className="btn btn-primary-purple">Open Module Configuration</Link>
    </div>
  );
}
