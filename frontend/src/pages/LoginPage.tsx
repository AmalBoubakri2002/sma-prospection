import { useState } from "react";
import { Form, Input, Button, Typography, App } from "antd";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import api from "@/utils/api";
import type { AuthUser } from "@/stores/authStore";
import { C, S, R } from "@/styles/tokens";

const { Title, Text } = Typography;

interface LoginForm { email: string; password: string; }

function ProspectAILogo() {
  return (
    <svg width="52" height="52" viewBox="0 0 52 52" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect width="52" height="52" rx="13" fill="url(#login-lg)" />
      <circle cx="26" cy="26" r="12"   stroke="white" strokeWidth="2"   fill="none" opacity="0.9" />
      <circle cx="26" cy="26" r="6.5"  stroke="white" strokeWidth="1.8" fill="none" opacity="0.7" />
      <circle cx="26" cy="26" r="2.2"  fill="white" />
      <line x1="26" y1="9"  x2="26" y2="13.5" stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.8" />
      <line x1="26" y1="38.5" x2="26" y2="43" stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.8" />
      <line x1="9"  y1="26" x2="13.5" y2="26" stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.8" />
      <line x1="38.5" y1="26" x2="43" y2="26" stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.8" />
      <defs>
        <linearGradient id="login-lg" x1="0" y1="0" x2="52" y2="52" gradientUnits="userSpaceOnUse">
          <stop stopColor="#2a4f9e" />
          <stop offset="1" stopColor="#6366f1" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export default function LoginPage() {
  const navigate = useNavigate();
  const setAuth  = useAuthStore((state) => state.setAuth);
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: LoginForm) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append("username", values.email);
      params.append("password", values.password);

      const { data: tokenData } = await api.post<{ access_token: string; token_type: string }>(
        "/auth/token",
        params,
        { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
      );

      const { data: user } = await api.get<AuthUser>("/auth/me", {
        headers: { Authorization: `Bearer ${tokenData.access_token}` },
      });

      setAuth(tokenData.access_token, user);
      navigate(user.role === "admin" ? "/admin" : "/commercial");
    } catch {
      message.error("Email ou mot de passe incorrect");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight:      "100vh",
        background:     C.bg,
        display:        "flex",
        alignItems:     "center",
        justifyContent: "center",
        padding:        24,
      }}
    >
      <div
        style={{
          width:        "100%",
          maxWidth:     420,
          background:   C.surface,
          borderRadius: R.xl,
          padding:      "44px 40px 36px",
          boxShadow:    S.modal,
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 6 }}>
          <ProspectAILogo />
          <div>
            <Title level={3} style={{ margin: 0, color: C.navy, fontWeight: 800, lineHeight: 1.2, fontSize: 22 }}>
              ProspectAI
            </Title>
            <Text style={{ color: C.textSub, fontSize: 12.5, fontWeight: 400 }}>
              SMA Prospection
            </Text>
          </div>
        </div>

        <Text style={{ display: "block", color: C.textMuted, fontSize: 13.5, marginBottom: 28, marginTop: 4 }}>
          Plateforme de prospection B2B automatisée
        </Text>

        <Form name="login" onFinish={onFinish} layout="vertical" size="large">
          <Form.Item
            label="Adresse email professionnelle"
            name="email"
            rules={[{ required: true, message: "Email requis" }]}
          >
            <Input placeholder="vous@entreprise.com" />
          </Form.Item>

          <Form.Item
            label="Mot de passe"
            name="password"
            rules={[{ required: true, message: "Mot de passe requis" }]}
            style={{ marginBottom: 4 }}
          >
            <Input.Password placeholder="••••••••" />
          </Form.Item>

          {/* Forgot */}
          <div style={{ textAlign: "right", marginBottom: 24 }}>
            <a
              href="#"
              style={{ color: "#3a6fc4", fontSize: 13, fontWeight: 500, textDecoration: "none" }}
              onMouseEnter={(e) => (e.currentTarget.style.textDecoration = "underline")}
              onMouseLeave={(e) => (e.currentTarget.style.textDecoration = "none")}
            >
              Mot de passe oublié ?
            </a>
          </div>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={loading}
              style={{ height: 48, fontSize: 15, letterSpacing: 0.2 }}
            >
              Se connecter
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: "center", marginTop: 24, borderTop: `1px solid ${C.border}`, paddingTop: 18 }}>
          <Text style={{ color: C.textFaint, fontSize: 12 }}>
            © 2026 ProspectAI · Tous droits réservés
          </Text>
        </div>
      </div>
    </div>
  );
}
