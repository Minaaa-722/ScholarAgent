import React, { useEffect, useState } from "react";
import { getCredentials, updateCredential, clearCredential } from "../api/client";
import Card from "../components/Card";
import Button from "../components/Button";
import Badge from "../components/Badge";
import { useToast } from "../components/Toast";

const CREDENTIAL_LABELS: Record<string, string> = {
  LLM_API_KEY: "LLM API Key",
  SEMANTIC_SCHOLAR_API_KEY: "Semantic Scholar API Key",
  GOOGLE_SCHOLAR_COOKIE: "Google Scholar Cookie",
};

const CREDENTIAL_DESCRIPTIONS: Record<string, string> = {
  LLM_API_KEY: "用于调用 LLM 供应商的 API（OpenAI 兼容接口）",
  SEMANTIC_SCHOLAR_API_KEY: "可选，用于 Semantic Scholar 检索（提升速率限制）",
  GOOGLE_SCHOLAR_COOKIE: "可选，用于 Google Scholar 补充检索",
};

type CredentialMap = Record<string, { configured: boolean; preview: string }>;

export default function Credentials() {
  const { showToast } = useToast();
  const [creds, setCreds] = useState<CredentialMap>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});

  const fetchCreds = async () => {
    try {
      setLoading(true);
      const data = await getCredentials();
      setCreds(data.credentials || {});
    } catch {
      showToast("error", "获取凭据状态失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCreds();
  }, []);

  const handleSave = async (key: string) => {
    const value = inputs[key]?.trim();
    if (!value) {
      showToast("error", "请输入有效的 API Key");
      return;
    }
    try {
      setSaving(key);
      await updateCredential(key, value);
      showToast("success", `${CREDENTIAL_LABELS[key]} 已保存到系统凭据管理器`);
      setInputs((prev) => ({ ...prev, [key]: "" }));
      await fetchCreds();
    } catch {
      showToast("error", "保存失败");
    } finally {
      setSaving(null);
    }
  };

  const handleClear = async (key: string) => {
    try {
      setSaving(key);
      await clearCredential(key);
      showToast("success", `${CREDENTIAL_LABELS[key]} 已清除`);
      await fetchCreds();
    } catch {
      showToast("error", "清除失败");
    } finally {
      setSaving(null);
    }
  };

  const isFirstRun = !loading && Object.values(creds).every((c) => !c.configured);

  const inputStyle: React.CSSProperties = {
    flex: 1,
    padding: "0.5rem 0.75rem",
    border: "1px solid var(--color-border, #ddd)",
    borderRadius: "var(--radius-md, 6px)",
    fontSize: "var(--font-size-sm, 14px)",
    fontFamily: "var(--font-family, sans-serif)",
    background: "var(--color-bg, #fff)",
    color: "var(--color-text, #333)",
  };

  return (
    <div>

      <h1 style={{ fontSize: "var(--font-size-2xl, 28px)", marginBottom: "var(--space-md, 12px)" }}>
        Credentials Management
      </h1>
      <p style={{ color: "var(--color-text-secondary, #666)", marginBottom: "var(--space-xl, 24px)" }}>
        管理 LLM API Key 等凭据。凭据安全存储在操作系统凭据管理器（加密），不会以明文形式写入文件。
      </p>

      {/* First-run guidance */}
      {isFirstRun && (
        <Card
          title="🔑 首次运行引导"
          style={{
            borderLeft: "4px solid #4fc3f7",
            marginBottom: "var(--space-xl, 24px)",
          }}
        >
          <p style={{ margin: 0, lineHeight: 1.6 }}>
            尚未配置任何 API Key。请在下表输入你的 LLM_API_KEY，系统会将其安全存储到
            <strong>操作系统凭据管理器</strong>（加密存储）。
          </p>
          <p style={{ margin: "8px 0 0", lineHeight: 1.6, fontSize: "0.9em", color: "#888" }}>
            提示：你也可以通过 <code>.env</code> 文件配置（项目根目录），但请注意 <code>.env</code> 是明文文件，
            生产环境建议优先使用本页面录入凭据。
          </p>
        </Card>
      )}

      {/* Credential rows */}
      {loading ? (
        <p>加载中...</p>
      ) : (
        Object.keys(CREDENTIAL_LABELS).map((key) => {
          const info = creds[key] || { configured: false, preview: "" };
          return (
            <Card
              key={key}
              title={CREDENTIAL_LABELS[key]}
              style={{ marginBottom: "var(--space-md, 12px)" }}
            >
              <div style={{ marginBottom: "var(--space-sm, 8px)" }}>
                <Badge
                  variant={info.configured ? "success" : "default"}
                  label={info.configured ? "已配置" : "未配置"}
                />
                {info.configured && (
                  <span
                    style={{
                      marginLeft: "12px",
                      fontSize: "var(--font-size-sm, 14px)",
                      color: "var(--color-text-secondary, #666)",
                      fontFamily: "monospace",
                    }}
                  >
                    当前值: {info.preview}
                  </span>
                )}
              </div>
              <p
                style={{
                  margin: "0 0 var(--space-sm, 8px)",
                  fontSize: "var(--font-size-sm, 14px)",
                  color: "var(--color-text-secondary, #666)",
                }}
              >
                {CREDENTIAL_DESCRIPTIONS[key]}
              </p>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <input
                  type="password"
                  placeholder={info.configured ? "输入新值以更新..." : "输入 API Key..."}
                  value={inputs[key] ?? ""}
                  onChange={(e) =>
                    setInputs((prev) => ({ ...prev, [key]: e.target.value }))
                  }
                  style={inputStyle}
                />
                <Button
                  variant="primary"
                  onClick={() => handleSave(key)}
                  disabled={saving === key}
                  label={saving === key ? "保存中..." : "保存"}
                />
                {info.configured && (
                  <Button
                    variant="danger"
                    onClick={() => handleClear(key)}
                    disabled={saving === key}
                    label="清除"
                  />
                )}
              </div>
            </Card>
          );
        })
      )}

      {/* Security note */}
      <Card
        title="🔒 安全说明"
        style={{
          marginTop: "var(--space-xl, 24px)",
          background: "var(--color-bg-secondary, #f5f5f5)",
        }}
      >
        <ul style={{ margin: 0, paddingLeft: "20px", lineHeight: 2 }}>
          <li>
            <strong>主要存储</strong>：凭据写入操作系统凭据管理器
            （Windows Credential Manager / macOS Keychain），加密存储，其他用户不可读。
          </li>
          <li>
            <strong>运行时缓存</strong>：写入后同时注入进程环境变量，供当前会话使用。
          </li>
          <li>
            <strong>兜底方案</strong>：支持通过 <code>.env</code>
            文件加载（项目根目录，参见 <code>.env.example</code>）。
            <span style={{ color: "#e67e22" }}>
              注意：.env 是明文文件，存在被其他进程读取的风险，建议仅用于开发环境。
            </span>
          </li>
          <li>
            <strong>查看状态</strong>：本页面仅显示凭据的"前 4 位字符 + ****"，绝不会回显完整凭据。
          </li>
          <li>
            <strong>安全承诺</strong>：凭据不会硬编码进源码，不会被提交进 Git 历史。
          </li>
        </ul>
      </Card>
    </div>
  );
}