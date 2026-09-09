import { useTranslation } from 'react-i18next';

interface Props {
  questions: string[];
  loading?: boolean;
  onPick: (question: string) => void;
  disabled?: boolean;
}

/** Clickable example-question chips shown while the thread is still empty. */
export default function SuggestedQuestions({ questions, loading, onPick, disabled }: Props) {
  const { t } = useTranslation('chat');
  if (loading) {
    return <p className="muted">{t('loadingExamples')}</p>;
  }
  if (questions.length === 0) return null;
  return (
    <div className="chip-row" aria-label={t('exampleQuestions')}>
      {questions.map((question) => (
        <button
          key={question}
          type="button"
          className="chip"
          onClick={() => onPick(question)}
          disabled={disabled}
        >
          {question}
        </button>
      ))}
    </div>
  );
}
