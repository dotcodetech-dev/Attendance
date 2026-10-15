import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "../components/Layout";
import { ModuleGate } from "../components/ModuleGate";
import { getToken } from "../store/auth";
import { CommandsPage } from "../pages/CommandsPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DevicesPage } from "../pages/DevicesPage";
import { EssLeavesPage } from "../pages/EssLeavesPage";
import { EssManualEntryPage } from "../pages/EssManualEntryPage";
import { LeaveApprovalsPage } from "../pages/LeaveApprovalsPage";
import { EssMyAttendancePage } from "../pages/EssMyAttendancePage";
import { EmployeesPage } from "../pages/EmployeesPage";
import { FaceAttendancePage } from "../pages/FaceAttendancePage";
import { HolidaysConfigPage } from "../pages/HolidaysConfigPage";
import { EnrollmentPage } from "../pages/EnrollmentPage";
import { LeavesConfigPage } from "../pages/LeavesConfigPage";
import { LoginPage } from "../pages/LoginPage";
import { LogsPage } from "../pages/LogsPage";
import { RosterConfigPage } from "../pages/RosterConfigPage";
import { CategoriesConfigPage } from "../pages/CategoriesConfigPage";
import { ShiftsConfigPage } from "../pages/ShiftsConfigPage";
import { AttendanceRulesPage } from "../pages/AttendanceRulesPage";
import { TransferPage } from "../pages/TransferPage";
import { UserRolesConfigPage } from "../pages/UserRolesConfigPage";
import { OrganizationConfigPage } from "../pages/OrganizationConfigPage";
import { MastersConfigPage } from "../pages/MastersConfigPage";
import { MessTokenPage } from "../pages/mess/MessTokenPage";
import { MessSettingsPage } from "../pages/mess/MessSettingsPage";
import { MessTokenReportPage } from "../pages/mess/MessTokenReportPage";
import { MessKioskPage } from "../pages/mess/MessKioskPage";
import { StudentsPage } from "../pages/students/StudentsPage";
import { StudentDashboardPage } from "../pages/students/StudentDashboardPage";
import { StudentAttendancePage } from "../pages/students/StudentAttendancePage";
import { StudentShiftsPage } from "../pages/students/StudentShiftsPage";
import { StudentLeavesPage } from "../pages/students/StudentLeavesPage";
import { StudentReportsPage } from "../pages/students/StudentReportsPage";
import { DailyAttendancePage } from "../pages/reports/DailyAttendancePage";
import { MonthlyRegisterPage } from "../pages/reports/MonthlyRegisterPage";
import { LeaveBalanceReportPage } from "../pages/reports/LeaveBalanceReportPage";
import { LateOtReportPage } from "../pages/reports/LateOtReportPage";
import { IndividualSheetPage } from "../pages/reports/IndividualSheetPage";
import { MusterTimePage } from "../pages/reports/MusterTimePage";
import { MusterLeavePage } from "../pages/reports/MusterLeavePage";
import { LateArrivalPage } from "../pages/reports/LateArrivalPage";
import { EarlyDeparturePage } from "../pages/reports/EarlyDeparturePage";
import { InOutListPage } from "../pages/reports/InOutListPage";
import { EmployeeListPage } from "../pages/reports/EmployeeListPage";

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const token = getToken();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="devices" element={<DevicesPage />} />
          <Route path="employees" element={<EmployeesPage />} />
          <Route path="enrollment" element={<EnrollmentPage />} />
          <Route path="face" element={<FaceAttendancePage />} />
          <Route path="transfer" element={<TransferPage />} />
          <Route path="commands" element={<CommandsPage />} />
          <Route path="logs" element={<LogsPage />} />
          {/* Reports */}
          <Route path="reports/daily" element={<DailyAttendancePage />} />
          <Route path="reports/register" element={<MonthlyRegisterPage />} />
          <Route path="reports/leave-balance" element={<LeaveBalanceReportPage />} />
          <Route path="reports/late-ot" element={<LateOtReportPage />} />
          <Route path="reports/individual" element={<IndividualSheetPage />} />
          <Route path="reports/muster-time" element={<MusterTimePage />} />
          <Route path="reports/muster-leave" element={<MusterLeavePage />} />
          <Route path="reports/late-arrival" element={<LateArrivalPage />} />
          <Route path="reports/early-departure" element={<EarlyDeparturePage />} />
          <Route path="reports/in-out" element={<InOutListPage />} />
          <Route path="reports/employee-list" element={<EmployeeListPage />} />
          {/* ESS portal preview */}
          <Route path="ess/my-attendance" element={<EssMyAttendancePage />} />
          <Route path="ess/my-leaves" element={<EssLeavesPage />} />
          <Route path="ess/leave-approvals" element={<LeaveApprovalsPage />} />
          <Route path="ess/leave-entry" element={<EssLeavesPage mode="admin" />} />
          <Route path="ess/manual-entry" element={<EssManualEntryPage />} />
          {/* Admin configuration */}
          <Route path="config/shifts" element={<ShiftsConfigPage />} />
          <Route path="config/attendance-rules" element={<AttendanceRulesPage />} />
          <Route path="config/rosters" element={<RosterConfigPage />} />
          <Route path="config/holidays" element={<HolidaysConfigPage />} />
          <Route path="config/leaves" element={<LeavesConfigPage />} />
          <Route path="config/categories" element={<CategoriesConfigPage />} />
          <Route path="config/roles" element={<UserRolesConfigPage />} />
          <Route path="config/organization" element={<OrganizationConfigPage />} />
          <Route path="config/masters" element={<MastersConfigPage />} />
          {/* Mess */}
          <Route path="mess/token" element={<ModuleGate feature="mess_tokens"><MessTokenPage /></ModuleGate>} />
          <Route path="mess/kiosk" element={<ModuleGate feature="mess_tokens"><MessKioskPage /></ModuleGate>} />
          <Route path="mess/report" element={<ModuleGate feature="mess_tokens"><MessTokenReportPage /></ModuleGate>} />
          <Route path="config/mess" element={<MessSettingsPage />} />
          {/* Mess and Students pages show a "module is off" screen while switched off in Module Configuration */}
          <Route path="students/dashboard" element={<ModuleGate feature="student_attendance"><StudentDashboardPage /></ModuleGate>} />
          <Route path="students" element={<ModuleGate feature="student_attendance"><StudentsPage /></ModuleGate>} />
          <Route path="students/attendance" element={<ModuleGate feature="student_attendance"><StudentAttendancePage /></ModuleGate>} />
          <Route path="students/shifts" element={<ModuleGate feature="student_attendance"><StudentShiftsPage /></ModuleGate>} />
          <Route path="students/leaves" element={<ModuleGate feature="student_leaves"><StudentLeavesPage /></ModuleGate>} />
          <Route path="students/reports" element={<ModuleGate feature="student_attendance"><StudentReportsPage /></ModuleGate>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
