import { Routes, Route, Navigate } from "react-router-dom";
import { Spin } from "antd";
import { useAuthStore, useAuthHydrated } from "@/stores/authStore";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import AdminLayout from "@/components/AdminLayout";
import AdminDashboardPage from "@/pages/admin/DashboardPage";
import UsersPage from "@/pages/admin/UsersPage";
import CommercialLayout from "@/components/CommercialLayout";
import CommercialDashboardPage from "@/pages/commercial/DashboardPage";
import NewCampaignPage from "@/pages/commercial/NewCampaignPage";
import ProfilePage from "@/pages/commercial/ProfilePage";
import ProtectedRoute from "@/components/ProtectedRoute";
import RequireActiveAccount from "@/components/RequireActiveAccount";

function RootRedirect() {
  const user = useAuthStore((state) => state.user);
  const token = useAuthStore((state) => state.token);
  if (!token) return <Navigate to="/login" replace />;
  return <Navigate to={user?.role === "admin" ? "/admin" : "/commercial"} replace />;
}

export default function App() {
  const hydrated = useAuthHydrated();

  if (!hydrated) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Commercial */}
      <Route
        path="/commercial"
        element={
          <ProtectedRoute requiredRole="commercial">
            <CommercialLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<CommercialDashboardPage />} />
        <Route path="profil" element={<ProfilePage />} />
        <Route
          path="campagnes/nouvelle"
          element={
            <RequireActiveAccount>
              <NewCampaignPage />
            </RequireActiveAccount>
          }
        />
      </Route>

      {/* Admin */}
      <Route
        path="/admin"
        element={
          <ProtectedRoute requiredRole="admin">
            <AdminLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<AdminDashboardPage />} />
        <Route path="commerciaux" element={<UsersPage />} />
      </Route>

      <Route path="*" element={<RootRedirect />} />
    </Routes>
  );
}
