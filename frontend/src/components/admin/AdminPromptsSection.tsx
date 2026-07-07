import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listPrompts, resetPrompt, updatePrompt } from '../../api/endpoints';
import type { PromptTemplate } from '../../api/types';
import { errorMessage } from '../../utils/format';
import { ErrorBanner, InfoBanner, Spinner } from '../ui';

/** Edit the AI system prompts used by the Ask and Analysis sections. */
export default function AdminPromptsSection() {
  const { t } = useTranslation('admin');
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string | null>>({});
  const [savedKey, setSavedKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const list = await listPrompts();
      setPrompts(list);
      setDrafts(Object.fromEntries(list.map((p) => [p.key, p.content])));
    } catch (err) {
      setLoadError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const applyResult = (updated: PromptTemplate) => {
    setPrompts((prev) => prev.map((p) => (p.key === updated.key ? updated : p)));
    setDrafts((prev) => ({ ...prev, [updated.key]: updated.content }));
  };

  const handleSave = async (prompt: PromptTemplate) => {
    setRowError((prev) => ({ ...prev, [prompt.key]: null }));
    setSavedKey(null);
    setBusyKey(prompt.key);
    try {
      applyResult(await updatePrompt(prompt.key, drafts[prompt.key] ?? ''));
      setSavedKey(prompt.key);
    } catch (err) {
      setRowError((prev) => ({ ...prev, [prompt.key]: errorMessage(err) }));
    } finally {
      setBusyKey(null);
    }
  };

  const handleReset = async (prompt: PromptTemplate) => {
    if (!window.confirm(t('prompts.confirmReset', { title: prompt.title }))) return;
    setRowError((prev) => ({ ...prev, [prompt.key]: null }));
    setSavedKey(null);
    setBusyKey(prompt.key);
    try {
      applyResult(await resetPrompt(prompt.key));
    } catch (err) {
      setRowError((prev) => ({ ...prev, [prompt.key]: errorMessage(err) }));
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <section className="card">
      <div className="page__header">
        <h2 className="page__title">{t('prompts.title')}</h2>
        <button type="button" className="btn btn--ghost" onClick={() => void load()}>
          {t('refresh')}
        </button>
      </div>
      <p className="muted">{t('prompts.description')}</p>

      <ErrorBanner message={loadError} />

      {loading ? (
        <Spinner label={t('prompts.loading')} />
      ) : (
        prompts.map((prompt) => {
          const draft = drafts[prompt.key] ?? '';
          const dirty = draft !== prompt.content;
          return (
            <div key={prompt.key} className="subsection">
              <h3>
                {prompt.title}{' '}
                {prompt.is_customized && (
                  <span className="pill pill--busy">{t('prompts.customized')}</span>
                )}
              </h3>
              <p className="muted">{prompt.description}</p>
              <textarea
                className="ask-input"
                rows={10}
                value={draft}
                onChange={(e) => setDrafts((prev) => ({ ...prev, [prompt.key]: e.target.value }))}
                aria-label={t('prompts.promptAria', { title: prompt.title })}
              />
              <div className="row-actions">
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={busyKey === prompt.key || !dirty || !draft.trim()}
                  onClick={() => void handleSave(prompt)}
                >
                  {busyKey === prompt.key ? t('prompts.working') : t('prompts.save')}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={busyKey === prompt.key || !prompt.is_customized}
                  onClick={() => void handleReset(prompt)}
                >
                  {t('prompts.resetToDefault')}
                </button>
              </div>
              {savedKey === prompt.key && <InfoBanner>{t('prompts.promptSaved')}</InfoBanner>}
              <ErrorBanner message={rowError[prompt.key] ?? null} />
            </div>
          );
        })
      )}
    </section>
  );
}
