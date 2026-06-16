import { useState } from "react";
import { Form, Input, Button, Typography, App, Result } from "antd";
import { Link, useNavigate } from "react-router-dom";
import api from "@/utils/api";
import { C, S, R } from "@/styles/tokens";

const { Title, Text } = Typography;

interface RegisterForm {
  full_name: string;
  email: string;
  password: string;
}

export default function RegisterPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const onFinish = async (values: RegisterForm) => {
    setLoading(true);
    try {
      await api.post("/auth/register", values);
      setSubmitted(true);
    } catch (err: any) {
      message.error(
        err.response?.status === 409
          ? "Cet email est déjà utilisé"
          : "Erreur lors de l'inscription"
      );
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
          maxWidth:     440,
          background:   C.surface,
          borderRadius: R.xl,
          padding:      "44px 40px 36px",
          boxShadow:    S.modal,
        }}
      >
        {submitted ? (
          <Result
            status="success"
            title="Demande envoyée"
            subTitle="Votre demande d'inscription a été transmise à un administrateur. Vous recevrez l'accès dès qu'elle sera validée."
            extra={
              <Button type="primary" onClick={() => navigate("/login")}>
                Retour à la connexion
              </Button>
            }
          />
        ) : (
          <>
            <Title level={3} style={{ margin: 0, color: C.navy, fontWeight: 800 }}>
              Créer un compte commercial
            </Title>
            <Text style={{ display: "block", color: C.textMuted, fontSize: 13.5, marginBottom: 28, marginTop: 8 }}>
              Votre compte devra être validé par un administrateur avant de pouvoir vous connecter.
            </Text>

            <Form name="register" onFinish={onFinish} layout="vertical" size="large">
              <Form.Item
                label="Nom complet"
                name="full_name"
                rules={[{ required: true, message: "Le nom est requis" }]}
              >
                <Input placeholder="Jean Dupont" />
              </Form.Item>

              <Form.Item
                label="Adresse email professionnelle"
                name="email"
                rules={[
                  { required: true, message: "Email requis" },
                  { type: "email", message: "Email invalide" },
                ]}
              >
                <Input placeholder="vous@entreprise.com" />
              </Form.Item>

              <Form.Item
                label="Mot de passe"
                name="password"
                rules={[
                  { required: true, message: "Mot de passe requis" },
                  { min: 8, message: "Minimum 8 caractères" },
                ]}
              >
                <Input.Password placeholder="Minimum 8 caractères" />
              </Form.Item>

              <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  loading={loading}
                  style={{ height: 48, fontSize: 15, letterSpacing: 0.2 }}
                >
                  Envoyer ma demande
                </Button>
              </Form.Item>
            </Form>

            <div style={{ textAlign: "center", marginTop: 24, borderTop: `1px solid ${C.border}`, paddingTop: 18 }}>
              <Text style={{ color: C.textMuted, fontSize: 13 }}>
                Déjà un compte ? <Link to="/login" style={{ color: "#3a6fc4", fontWeight: 600 }}>Se connecter</Link>
              </Text>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
