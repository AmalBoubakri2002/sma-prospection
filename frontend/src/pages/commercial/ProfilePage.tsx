import { useState } from "react";
import { Typography, Form, Input, Button, Tag, App } from "antd";
import {
  UserOutlined, MailOutlined, ClockCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined, SaveOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "@/stores/authStore";
import api from "@/utils/api";
import { C, S, R } from "@/styles/tokens";

const { Title, Text } = Typography;

function StatusBanner({ status }: { status: string }) {
  if (status === "PENDING") {
    return (
      <div style={{
        background: C.amberBg, border: `1px solid ${C.amber}40`, borderRadius: R.lg,
        padding: "14px 18px", marginBottom: 24, display: "flex", gap: 12, alignItems: "flex-start",
      }}>
        <ClockCircleOutlined style={{ color: C.amber, fontSize: 18, marginTop: 2 }} />
        <div>
          <Text style={{ fontWeight: 700, color: C.amber, fontSize: 13.5, display: "block" }}>
            En attente d'approbation
          </Text>
          <Text style={{ fontSize: 13, color: C.text }}>
            Votre compte est en attente de validation par un administrateur. Certaines fonctionnalités restent indisponibles.
          </Text>
        </div>
      </div>
    );
  }
  if (status === "REJECTED") {
    return (
      <div style={{
        background: C.redBg, border: `1px solid ${C.red}40`, borderRadius: R.lg,
        padding: "14px 18px", marginBottom: 24, display: "flex", gap: 12, alignItems: "flex-start",
      }}>
        <CloseCircleOutlined style={{ color: C.red, fontSize: 18, marginTop: 2 }} />
        <div>
          <Text style={{ fontWeight: 700, color: C.red, fontSize: 13.5, display: "block" }}>
            Demande refusée
          </Text>
          <Text style={{ fontSize: 13, color: C.text }}>
            Votre demande d'inscription a été refusée par un administrateur.
          </Text>
        </div>
      </div>
    );
  }
  return (
    <div style={{
      background: C.greenBg, border: `1px solid ${C.green}40`, borderRadius: R.lg,
      padding: "14px 18px", marginBottom: 24, display: "flex", gap: 12, alignItems: "flex-start",
    }}>
      <CheckCircleOutlined style={{ color: C.green, fontSize: 18, marginTop: 2 }} />
      <div>
        <Text style={{ fontWeight: 700, color: C.green, fontSize: 13.5, display: "block" }}>
          Compte actif
        </Text>
        <Text style={{ fontSize: 13, color: C.text }}>
          Votre compte a été validé. Vous avez accès à toutes les fonctionnalités.
        </Text>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { message } = App.useApp();
  const user = useAuthStore((s) => s.user);
  const setAuth = useAuthStore((s) => s.setAuth);
  const token = useAuthStore((s) => s.token);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<{ full_name: string }>();

  const onFinish = async (values: { full_name: string }) => {
    if (!token || !user) return;
    setSaving(true);
    try {
      const { data } = await api.patch("/auth/me", { full_name: values.full_name });
      setAuth(token, { ...user, full_name: data.full_name });
      message.success("Profil mis à jour");
    } catch {
      message.error("Erreur lors de la mise à jour du profil");
    } finally {
      setSaving(false);
    }
  };

  if (!user) return null;

  return (
    <div className="page-root" style={{ maxWidth: 560 }}>
      <Title level={3} style={{ margin: 0, color: C.navy, fontWeight: 800, marginBottom: 24 }}>
        Mon profil
      </Title>

      <StatusBanner status={user.status} />

      <div style={{
        background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`,
        boxShadow: S.card, padding: "26px 28px",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <MailOutlined style={{ color: C.textMuted }} />
          <Text style={{ fontSize: 13.5, color: C.textMuted }}>{user.email}</Text>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 22 }}>
          <Text style={{ fontSize: 13, color: C.textMuted }}>Statut du compte :</Text>
          <Tag color={user.status === "ACTIVE" ? "success" : user.status === "REJECTED" ? "error" : "warning"}>
            {user.status === "ACTIVE" ? "Actif" : user.status === "REJECTED" ? "Refusé" : "En attente"}
          </Tag>
        </div>

        <Form
          form={form}
          layout="vertical"
          initialValues={{ full_name: user.full_name ?? "" }}
          onFinish={onFinish}
          size="large"
        >
          <Form.Item
            label="Nom complet"
            name="full_name"
            rules={[{ required: true, message: "Le nom est requis" }]}
          >
            <Input prefix={<UserOutlined style={{ color: C.textFaint }} />} placeholder="Jean Dupont" />
          </Form.Item>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>
            Enregistrer
          </Button>
        </Form>
      </div>
    </div>
  );
}
