import { Fragment, useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../api';
import type { ProviderInfo, ProviderTestResult } from '../types';
import { coerceNumber, errorMessage } from '../format';
import { ErrorNote } from './common';

type TestState = { state: 'running' } | { state: 'done'; result: ProviderTestResult };

const EMPTY_FORM = { name: '', base_url: '', model: '', api_key: '', priority: '' };

export default function ProvidersTab() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [note, setNote] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [tests, setTests] = useState<Record<string, TestState>>({});
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [formError, setFormError] = useState<string | null>(null);
  const [formOk, setFormOk] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listProviders();
      setProviders(res.providers ?? []);
      setNote(typeof res.note === 'string' ? res.note : '');
      setListError(null);
    } catch (err) {
      setListError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleEnabled = async (p: ProviderInfo) => {
    setBusy((prev) => ({ ...prev, [p.name]: true }));
    try {
      await api.patchProvider(p.name, { enabled: !p.enabled });
      await load();
    } catch (err) {
      setListError(`Failed to update "${p.name}": ${errorMessage(err)}`);
    } finally {
      setBusy((prev) => ({ ...prev, [p.name]: false }));
    }
  };

  const removeProvider = async (p: ProviderInfo) => {
    if (!window.confirm(`Delete provider "${p.name}"?`)) return;
    setBusy((prev) => ({ ...prev, [p.name]: true }));
    try {
      await api.deleteProvider(p.name);
      await load();
    } catch (err) {
      setListError(`Failed to delete "${p.name}": ${errorMessage(err)}`);
    } finally {
      setBusy((prev) => ({ ...prev, [p.name]: false }));
    }
  };

  const testProvider = async (name: string) => {
    setTests((prev) => ({ ...prev, [name]: { state: 'running' } }));
    try {
      const result = await api.testProvider(name);
      setTests((prev) => ({ ...prev, [name]: { state: 'done', result } }));
    } catch (err) {
      setTests((prev) => ({
        ...prev,
        [name]: {
          state: 'done',
          result: { provider: name, model: '', ok: false, latency_ms: null, signals_found: [], error: errorMessage(err) },
        },
      }));
    }
  };

  const submitForm = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError(null);
    setFormOk(null);
    const name = form.name.trim();
    const baseUrl = form.base_url.trim();
    const model = form.model.trim();
    if (!name || !baseUrl || !model) {
      setFormError('Name, base URL and model are required.');
      return;
    }
    let priority: number | undefined;
    if (form.priority.trim() !== '') {
      const n = coerceNumber(form.priority);
      if (n == null || n < 0) {
        setFormError('Priority must be a non-negative number.');
        return;
      }
      priority = Math.round(n);
    }
    setSaving(true);
    try {
      await api.upsertProvider({
        name,
        base_url: baseUrl,
        model,
        api_key: form.api_key.trim() || undefined,
        priority,
        enabled: true,
      });
      setFormOk(`Provider "${name}" saved. Keys persist in data/providers.json.`);
      setForm((prev) => ({ ...prev, api_key: '' }));
      await load();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="tab-body">
      <div className="toolbar">
        <h2 className="toolbar-title">LLM providers</h2>
        <span className="spacer" />
        <button type="button" className="btn" onClick={() => void load()} disabled={loading}>
          {loading ? 'Loading…' : 'Reload'}
        </button>
      </div>

      {listError && <ErrorNote>{listError}</ErrorNote>}

      <div className="panel table-panel">
        <table className="tbl providers-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Model</th>
              <th>Endpoint</th>
              <th>Kind</th>
              <th>Priority</th>
              <th>Key</th>
              <th>Enabled</th>
              <th>Test</th>
            </tr>
          </thead>
          <tbody>
            {providers.length === 0 && !loading ? (
              <tr>
                <td colSpan={8} className="muted center">No providers configured yet — add one below.</td>
              </tr>
            ) : (
              providers.map((p) => {
                const t = tests[p.name];
                return (
                  <Fragment key={p.name}>
                    <tr>
                      <td className="mono">{p.name}</td>
                      <td className="mono">{p.model}</td>
                      <td className="mono endpoint-cell" title={p.base_url}>{p.base_url}</td>
                      <td>
                        <span className={`chip kind-${p.kind === 'local' ? 'local' : 'cloud'}`}>{p.kind}</span>
                      </td>
                      <td>{p.priority ?? '—'}</td>
                      <td className="muted">{p.has_key ? p.key_hint || 'key set' : 'no key'}</td>
                      <td>
                        <label
                          className="switch"
                          title={p.enabled ? 'Enabled — click to disable' : 'Disabled — click to enable'}
                        >
                          <input
                            type="checkbox"
                            checked={p.enabled}
                            disabled={busy[p.name]}
                            onChange={() => void toggleEnabled(p)}
                          />
                          <span className="slider" />
                        </label>
                      </td>
                      <td>
                        <div className="row-actions">
                          <button type="button" className="btn btn-small" onClick={() => void testProvider(p.name)}>
                            Test
                          </button>
                          <button
                            type="button"
                            className="btn btn-small btn-danger"
                            onClick={() => void removeProvider(p)}
                            disabled={busy[p.name]}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                    {t && (
                      <tr className="test-result-row">
                        <td colSpan={8}>
                          {t.state === 'running' ? (
                            <span className="muted">Testing &ldquo;{p.name}&rdquo;&hellip;</span>
                          ) : t.result.ok ? (
                            <span className="test-ok">
                              OK —{' '}
                              {t.result.latency_ms != null
                                ? `${Math.round(t.result.latency_ms)} ms`
                                : 'latency unknown'}
                              {t.result.signals_found.length > 0
                                ? ` · signals: ${t.result.signals_found.join(', ')}`
                                : ' · no signals found'}
                            </span>
                          ) : (
                            <span className="test-fail">
                              FAILED{t.result.error ? ` — ${t.result.error}` : ''}
                            </span>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <section className="panel form-panel">
        <header className="panel-head">
          <h2>Add / Update provider</h2>
        </header>
        <form className="provider-form" onSubmit={(e) => void submitForm(e)}>
          <div className="form-grid">
            <label>
              <span>Name</span>
              <input
                className="input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="groq-primary"
                required
              />
            </label>
            <label>
              <span>Base URL</span>
              <input
                className="input"
                value={form.base_url}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                placeholder="https://api.groq.com/openai/v1"
                required
              />
            </label>
            <label>
              <span>Model</span>
              <input
                className="input"
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                placeholder="llama-3.3-70b-versatile"
                required
              />
            </label>
            <label>
              <span>API key</span>
              <input
                className="input"
                type="password"
                autoComplete="off"
                value={form.api_key}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                placeholder="(leave blank to keep existing)"
              />
            </label>
            <label>
              <span>Priority</span>
              <input
                className="input"
                type="number"
                min={0}
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value })}
                placeholder="10"
              />
            </label>
          </div>
          {formError && <ErrorNote>{formError}</ErrorNote>}
          {formOk && <div className="ok-note">{formOk}</div>}
          <div className="form-foot">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Save provider'}
            </button>
          </div>
          <p className="form-caption">
            Works with ANY OpenAI-compatible endpoint (Groq, Gemini OpenAI-compat, OpenRouter, Alibaba DashScope,
            Ollama /v1, LiteLLM&hellip;). Keys persist in data/providers.json
          </p>
        </form>
      </section>

      {note && <p className="muted small server-note">{note}</p>}
    </div>
  );
}
