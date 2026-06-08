import axios from "axios";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

// Interceptors JWT (attach token, handle 401) — à ajouter à l'étape auth

export default api;
