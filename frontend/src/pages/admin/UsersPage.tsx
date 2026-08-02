import { useEffect, useState } from "react";
import {
  Typography, Button, Table, Tag, Modal,
  Form, Input, App, Popconfirm, Tooltip, Space, Avatar,
} from "antd";
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  CheckCircleOutlined, StopOutlined, ClockCircleOutlined, CloseCircleOutlined,
  SearchOutlined, TeamOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import axios from "axios";
import api from "@/utils/api";
import { C, S, R } from "@/styles/tokens";

const { Title, Text } = Typography;

type CommercialStatus = "PENDING" | "ACTIVE" | "REJECTED";

interface Commercial {
  id:         string;
  email:      string;
  full_name:  string | null;
  role:       string;
  status:     CommercialStatus;
  created_at: string;
}

interface CreateForm { full_name: string; email: string; password: string; }

function getInitials(name: string | null, email: string): string {
  if (name) {
    const parts = name.trim().split(" ");
    return parts.length >= 2
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : parts[0][0].toUpperCase();
  }
  return email[0].toUpperCase();
}

const AVATAR_PALETTE = [C.indigo, C.cyan, C.purple, C.amber, C.green, C.navy];
function avatarColor(id: string): string {
  const idx = id.charCodeAt(0) % AVATAR_PALETTE.length;
  return AVATAR_PALETTE[idx];
}

export default function UsersPage() {
  const { message } = App.useApp();
  const [users,    setUsers]    = useState<Commercial[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [search,   setSearch]   = useState("");

  const [createOpen,    setCreateOpen]    = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createForm]  = Form.useForm<CreateForm>();

  const [editUser,    setEditUser]    = useState<Commercial | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editForm]  = Form.useForm<{ full_name: string }>();

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await api.get<Commercial[]>("/users/");
      setUsers(res.data);
    } catch {
      message.error("Impossible de charger les commerciaux");
    } finally {
      setLoading(false);
    }
  };

  // Chargement unique au montage — fetchUsers est recréée à chaque rendu mais
  // ne dépend que du singleton `api`, l'inclure redéclencherait l'effet en boucle.
  useEffect(() => { fetchUsers(); }, []);

  const handleCreate = async (values: CreateForm) => {
    setCreateLoading(true);
    try {
      await api.post("/users/", { ...values, role: "commercial" });
      message.success("Compte commercial créé avec succès");
      setCreateOpen(false);
      createForm.resetFields();
      fetchUsers();
    } catch (err) {
      message.error(
        axios.isAxiosError(err) && err.response?.status === 409
          ? "Cet email est déjà utilisé"
          : "Erreur lors de la création"
      );
    } finally {
      setCreateLoading(false);
    }
  };

  const handleEdit = async (values: { full_name: string }) => {
    if (!editUser) return;
    setEditLoading(true);
    try {
      await api.patch(`/users/${editUser.id}`, { full_name: values.full_name });
      message.success("Nom mis à jour");
      setEditUser(null);
      editForm.resetFields();
      fetchUsers();
    } catch {
      message.error("Erreur lors de la mise à jour");
    } finally {
      setEditLoading(false);
    }
  };

  const handleApprove = async (user: Commercial) => {
    try {
      await api.post(`/users/${user.id}/approve`);
      message.success(user.status === "PENDING" ? "Compte approuvé" : "Compte réactivé");
      fetchUsers();
    } catch {
      message.error("Erreur lors de la validation du compte");
    }
  };

  const handleReject = async (user: Commercial) => {
    try {
      await api.post(`/users/${user.id}/reject`);
      message.success(user.status === "PENDING" ? "Demande refusée" : "Compte désactivé");
      fetchUsers();
    } catch {
      message.error("Erreur lors de la mise à jour du statut");
    }
  };

  const handleDelete = async (user: Commercial) => {
    try {
      await api.delete(`/users/${user.id}`);
      message.success("Compte supprimé");
      fetchUsers();
    } catch {
      message.error("Erreur lors de la suppression");
    }
  };

  const filtered = users.filter(
    (u) =>
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      (u.full_name ?? "").toLowerCase().includes(search.toLowerCase())
  );

  const activeCount   = users.filter((u) => u.status === "ACTIVE").length;
  const pendingCount  = users.filter((u) => u.status === "PENDING").length;
  const rejectedCount = users.filter((u) => u.status === "REJECTED").length;

  const columns: ColumnsType<Commercial> = [
    {
      title: "Commercial",
      key: "full_name",
      render: (_, record) => {
        const color = avatarColor(record.id);
        return (
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Avatar
              size={36}
              style={{ background: `${color}18`, color, fontSize: 13, fontWeight: 700, flexShrink: 0, border: `1.5px solid ${color}30` }}
            >
              {getInitials(record.full_name, record.email)}
            </Avatar>
            <div>
              <div style={{ fontWeight: 600, color: C.navy, fontSize: 14, lineHeight: 1.3 }}>
                {record.full_name ?? (
                  <span style={{ color: C.textFaint, fontStyle: "italic", fontWeight: 400 }}>Non renseigné</span>
                )}
              </div>
              <div style={{ fontSize: 12, color: C.textMuted, marginTop: 1 }}>{record.email}</div>
            </div>
          </div>
        );
      },
    },
    {
      title: "Statut",
      key: "status",
      width: 130,
      render: (_, record) => {
        if (record.status === "PENDING") {
          return <Tag icon={<ClockCircleOutlined />} color="warning">En attente</Tag>;
        }
        if (record.status === "REJECTED") {
          return <Tag icon={<CloseCircleOutlined />} color="error">Refusé</Tag>;
        }
        return <Tag icon={<CheckCircleOutlined />} color="success">Actif</Tag>;
      },
    },
    {
      title: "Création",
      key: "created_at",
      width: 140,
      render: (_, record) => (
        <Text style={{ fontSize: 13, color: C.textMuted }}>
          {new Date(record.created_at).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" })}
        </Text>
      ),
    },
    {
      title: "Actions",
      key: "actions",
      width: 180,
      align: "center",
      render: (_, record) => (
        <Space size={4}>
          <Tooltip title="Modifier le nom">
            <Button
              type="text"
              icon={<EditOutlined />}
              size="small"
              style={{ color: C.navy }}
              onClick={() => {
                setEditUser(record);
                editForm.setFieldsValue({ full_name: record.full_name ?? "" });
              }}
            />
          </Tooltip>
          {record.status === "PENDING" ? (
            <>
              <Tooltip title="Approuver la demande">
                <Button
                  type="text"
                  size="small"
                  icon={<CheckCircleOutlined />}
                  style={{ color: C.green }}
                  onClick={() => handleApprove(record)}
                />
              </Tooltip>
              <Tooltip title="Refuser la demande">
                <Button
                  type="text"
                  size="small"
                  icon={<CloseCircleOutlined />}
                  style={{ color: C.red }}
                  onClick={() => handleReject(record)}
                />
              </Tooltip>
            </>
          ) : (
            <Tooltip title={record.status === "ACTIVE" ? "Désactiver" : "Réactiver"}>
              <Button
                type="text"
                size="small"
                icon={record.status === "ACTIVE" ? <StopOutlined /> : <CheckCircleOutlined />}
                style={{ color: record.status === "ACTIVE" ? C.red : C.green }}
                onClick={() => (record.status === "ACTIVE" ? handleReject(record) : handleApprove(record))}
              />
            </Tooltip>
          )}
          <Tooltip title="Supprimer">
            <Popconfirm
              title="Supprimer ce compte ?"
              description="Cette action est irréversible."
              onConfirm={() => handleDelete(record)}
              okText="Supprimer"
              cancelText="Annuler"
              okButtonProps={{ danger: true }}
            >
              <Button type="text" size="small" icon={<DeleteOutlined />} danger />
            </Popconfirm>
          </Tooltip>
        </Space>
      ),
    },
  ];

  const inputShared: React.CSSProperties = { borderRadius: R.md };

  return (
    <div className="page-root">

      {/* ── Page header ────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28, flexWrap: "wrap", gap: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0, color: C.navy, fontWeight: 800 }}>Commerciaux</Title>
          <div style={{ display: "flex", gap: 12, marginTop: 6, flexWrap: "wrap" }}>
            <Text style={{ fontSize: 13, color: C.textMuted }}>
              <span style={{ fontWeight: 700, color: C.navy }}>{users.length}</span> compte{users.length !== 1 ? "s" : ""} au total
            </Text>
            <Text style={{ fontSize: 13, color: C.green, fontWeight: 500 }}>● {activeCount} actif{activeCount !== 1 ? "s" : ""}</Text>
            {pendingCount > 0 && (
              <Text style={{ fontSize: 13, color: C.amber, fontWeight: 500 }}>● {pendingCount} en attente</Text>
            )}
            {rejectedCount > 0 && (
              <Text style={{ fontSize: 13, color: C.red, fontWeight: 500 }}>● {rejectedCount} refusé{rejectedCount !== 1 ? "s" : ""}</Text>
            )}
          </div>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          Nouveau commercial
        </Button>
      </div>

      {/* ── Table card ─────────────────────────────────────── */}
      <div style={{ background: C.surface, borderRadius: R.card, border: `1px solid ${C.border}`, boxShadow: S.card, overflow: "hidden" }}>

        {/* Toolbar */}
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 12 }}>
          <Input
            prefix={<SearchOutlined style={{ color: C.textFaint }} />}
            placeholder="Rechercher par nom ou email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ maxWidth: 300, borderRadius: R.md }}
            allowClear
          />
          {search && (
            <Text style={{ fontSize: 13, color: C.textMuted }}>
              {filtered.length} résultat{filtered.length !== 1 ? "s" : ""}
            </Text>
          )}
        </div>

        <Table
          dataSource={filtered}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: false, style: { padding: "8px 16px" } }}
          locale={{ emptyText: (
            <div style={{ padding: "40px 0", textAlign: "center" }}>
              <TeamOutlined style={{ fontSize: 36, color: C.textFaint, display: "block", marginBottom: 12 }} />
              <Text style={{ color: C.textMuted, fontSize: 14 }}>
                {search ? "Aucun résultat pour cette recherche" : "Aucun commercial pour l'instant"}
              </Text>
            </div>
          )}}
          style={{ borderRadius: 0 }}
        />
      </div>

      {/* ── Modal : Créer ───────────────────────────────────── */}
      <Modal
        title="Nouveau compte commercial"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        footer={null}
        width={440}
        centered
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate} size="large" style={{ marginTop: 4 }}>
          <Form.Item label="Nom complet" name="full_name" rules={[{ required: true, message: "Le nom est requis" }]}>
            <Input placeholder="Jean Dupont" style={inputShared} />
          </Form.Item>
          <Form.Item
            label="Adresse email"
            name="email"
            rules={[{ required: true, message: "L'email est requis" }, { type: "email", message: "Email invalide" }]}
          >
            <Input placeholder="jean.dupont@entreprise.com" style={inputShared} />
          </Form.Item>
          <Form.Item
            label="Mot de passe"
            name="password"
            rules={[{ required: true, message: "Le mot de passe est requis" }, { min: 8, message: "Minimum 8 caractères" }]}
          >
            <Input.Password placeholder="Minimum 8 caractères" style={inputShared} />
          </Form.Item>
          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", paddingTop: 4 }}>
            <Button onClick={() => { setCreateOpen(false); createForm.resetFields(); }}>Annuler</Button>
            <Button type="primary" htmlType="submit" loading={createLoading}>Créer le compte</Button>
          </div>
        </Form>
      </Modal>

      {/* ── Modal : Modifier ────────────────────────────────── */}
      <Modal
        title="Modifier le commercial"
        open={!!editUser}
        onCancel={() => { setEditUser(null); editForm.resetFields(); }}
        footer={null}
        width={400}
        centered
      >
        <Form form={editForm} layout="vertical" onFinish={handleEdit} size="large" style={{ marginTop: 4 }}>
          <Form.Item label="Nom complet" name="full_name" rules={[{ required: true, message: "Le nom est requis" }]}>
            <Input placeholder="Jean Dupont" style={inputShared} />
          </Form.Item>
          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", paddingTop: 4 }}>
            <Button onClick={() => { setEditUser(null); editForm.resetFields(); }}>Annuler</Button>
            <Button type="primary" htmlType="submit" loading={editLoading}>Enregistrer</Button>
          </div>
        </Form>
      </Modal>

    </div>
  );
}
