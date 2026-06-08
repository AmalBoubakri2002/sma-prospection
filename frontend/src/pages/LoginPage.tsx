import { Form, Input, Button, Card, Typography } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

const { Title } = Typography;

interface LoginForm {
  username: string;
  password: string;
}

export default function LoginPage() {
  const navigate = useNavigate();

  const onFinish = async (values: LoginForm) => {
    // TODO: appeler POST /api/v1/auth/token
    console.log("Login:", values);
    navigate("/home");
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      }}
    >
      <Card style={{ width: 380, borderRadius: 12 }}>
        <Title level={3} style={{ textAlign: "center", marginBottom: 24 }}>
          SMA Prospection
        </Title>
        <Form name="login" onFinish={onFinish} layout="vertical" size="large">
          <Form.Item name="username" rules={[{ required: true, message: "Identifiant requis" }]}>
            <Input prefix={<UserOutlined />} placeholder="Email" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "Mot de passe requis" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="Mot de passe" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              Se connecter
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
