import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";

interface Props {
  children: React.ReactNode;
}

export default function RequireActiveAccount({ children }: Props) {
  const user = useAuthStore((state) => state.user);
  if (user?.status !== "ACTIVE") return <Navigate to="/commercial" replace />;
  return <>{children}</>;
}
