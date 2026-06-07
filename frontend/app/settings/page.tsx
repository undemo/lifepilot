"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Save, Trash2 } from "lucide-react";
import { AppShell, PageHeader } from "@/components/common/AppShell";
import { ErrorState } from "@/components/common/States";
import { api, ApiClientError } from "@/lib/api";
import { clearPlanHistory } from "@/lib/plan-history";
import type { LLMSettings, StandardError } from "@/types/schema";

type FormState = {
  provider: string;
  enabled: boolean;
  base_url: string;
  model: string;
  temperature: string;
  max_tokens: string;
  timeout: string;
  retry: string;
  enable_thinking: boolean;
  credential: string;
};

function toForm(settings: LLMSettings): FormState {
  return {
    provider: settings.provider,
    enabled: settings.enabled,
    base_url: settings.base_url,
    model: settings.model,
    temperature: String(settings.temperature),
    max_tokens: String(settings.max_tokens),
    timeout: String(settings.timeout),
    retry: String(settings.retry),
    enable_thinking: settings.enable_thinking,
    credential: ""
  };
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [error, setError] = useState<StandardError | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [plansCleared, setPlansCleared] = useState(false);

  useEffect(() => {
    api
      .getLlmSettings()
      .then(({ data }) => {
        setSettings(data);
        setForm(toForm(data));
      })
      .catch((err) => {
        setError(err instanceof ApiClientError ? err.error : { code: "INTERNAL_ERROR", user_message: "设置读取失败。" });
      })
      .finally(() => setLoading(false));
  }, []);

  const selected = useMemo(
    () => settings?.available_providers.find((item) => item.provider === form?.provider),
    [settings?.available_providers, form?.provider]
  );

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setSaved(false);
  }

  function selectProvider(provider: string) {
    const option = settings?.available_providers.find((item) => item.provider === provider);
    setForm((current) =>
      current
        ? {
            ...current,
            provider,
            base_url: option?.default_base_url || current.base_url,
            model: option?.default_model || current.model
          }
        : current
    );
    setSaved(false);
  }

  async function save() {
    if (!form || saving) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const payload = {
        provider: form.provider,
        enabled: form.enabled,
        base_url: form.base_url,
        model: form.model,
        temperature: Number(form.temperature),
        max_tokens: Number(form.max_tokens),
        timeout: Number(form.timeout),
        retry: Number(form.retry),
        enable_thinking: form.enable_thinking,
        ...(form.credential.trim() ? { credential: form.credential.trim() } : {})
      };
      const { data } = await api.updateLlmSettings(payload);
      setSettings(data);
      setForm(toForm(data));
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "INTERNAL_ERROR", user_message: "设置保存失败。" });
    } finally {
      setSaving(false);
    }
  }

  function clearPlans() {
    clearPlanHistory();
    setPlansCleared(true);
  }

  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="Settings" title="模型接口设置" subtitle="切换受控LLM提供方，普通业务页不会显示底层凭证或推理链。" />
        {loading ? <section className="card"><div className="skeleton" /></section> : null}
        {form && settings ? (
          <>
            <section className="card">
              <div className="row-between">
                <strong>当前接口</strong>
                <span className={form.enabled ? "badge" : "badge gray"}>{form.enabled ? "启用" : "停用"}</span>
              </div>
              <div className="provider-grid">
                {settings.available_providers.map((option) => (
                  <button
                    key={option.provider}
                    className={option.provider === form.provider ? "provider-option active" : "provider-option"}
                    onClick={() => selectProvider(option.provider)}
                  >
                    <span>{option.label}</span>
                    {option.provider === form.provider ? <Check size={16} /> : null}
                  </button>
                ))}
              </div>
              <p className="subtitle small">凭证：{settings.credential_configured ? settings.credential_mask : "未配置"}</p>
            </section>

            <section className="card">
              <label className="field">
                <span>Base URL</span>
                <input className="input" value={form.base_url} onChange={(event) => update("base_url", event.target.value)} />
              </label>
              <label className="field">
                <span>Model</span>
                <input className="input" value={form.model} onChange={(event) => update("model", event.target.value)} />
              </label>
              <label className="field">
                <span>访问凭证</span>
                <input className="input" type="password" value={form.credential} placeholder="留空不修改" onChange={(event) => update("credential", event.target.value)} />
              </label>
              <div className="grid-2">
                <label className="field">
                  <span>Temperature</span>
                  <input className="input" inputMode="decimal" value={form.temperature} onChange={(event) => update("temperature", event.target.value)} />
                </label>
                <label className="field">
                  <span>Max tokens</span>
                  <input className="input" inputMode="numeric" value={form.max_tokens} onChange={(event) => update("max_tokens", event.target.value)} />
                </label>
                <label className="field">
                  <span>Timeout</span>
                  <input className="input" inputMode="decimal" value={form.timeout} onChange={(event) => update("timeout", event.target.value)} />
                </label>
                <label className="field">
                  <span>Retry</span>
                  <input className="input" inputMode="numeric" value={form.retry} onChange={(event) => update("retry", event.target.value)} />
                </label>
              </div>
              <label className="toggle-row">
                <input type="checkbox" checked={form.enabled} onChange={(event) => update("enabled", event.target.checked)} />
                <span>启用接口</span>
              </label>
              <label className="toggle-row">
                <input type="checkbox" checked={form.enable_thinking} onChange={(event) => update("enable_thinking", event.target.checked)} />
                <span>思考模式</span>
              </label>
              <button className="button full" disabled={saving || !selected} onClick={save}>
                {saving ? "保存中" : "保存设置"}
                <Save size={18} />
              </button>
              {saved ? <p className="subtitle small">已保存到当前运行环境。</p> : null}
            </section>

          </>
        ) : null}
        <section className="card">
          <div className="section-title">
            <h2>计划记录</h2>
            <span className="badge gray">本机</span>
          </div>
          <p className="subtitle">清空计划页里的历史卡片、最近生成和未完成生成记录。</p>
          <button className="button secondary full" onClick={clearPlans} type="button">
            <Trash2 size={18} />
            清空计划记录
          </button>
          {plansCleared ? <p className="subtitle small">已清空，回到计划页会显示空状态。</p> : null}
        </section>
        <ErrorState error={error} debug />
      </div>
    </AppShell>
  );
}
