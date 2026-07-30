import axios from "axios";
import { useAuthStore } from "@/stores/authStore";

// En dev, le proxy Vite (voir vite.config.ts) redirige "/api" vers le backend
// local : baseURL relative suffit. En prod (frontend et backend sur des
// domaines différents), VITE_API_URL doit pointer vers l'origine du backend.
const backendOrigin = import.meta.env.VITE_API_URL ?? "";

const api = axios.create({
  baseURL: `${backendOrigin}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().clearAuth();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;
