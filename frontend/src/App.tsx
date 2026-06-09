import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import LoginPage from "@/pages/LoginPage";
import AdminLayout from "@/components/AdminLayout";
import AdminDashboardPage from "@/pages/admin/DashboardPage";
import UsersPage from "@/pages/admin/UsersPage";
import CommercialLayout from "@/components/CommercialLayout";
import CommercialDashboardPage from "@/pages/commercial/DashboardPage";
import ProtectedRoute from "@/components/ProtectedRoute";

function RootRedirect() {
  const user = useAuthStore((state) => state.user);
  const token = useAuthStore((state) => state.token);
  if (!token) return <Navigate to="/login" replace />;
  return <Navigate to={user?.role === "admin" ? "/admin" : "/commercial"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

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
