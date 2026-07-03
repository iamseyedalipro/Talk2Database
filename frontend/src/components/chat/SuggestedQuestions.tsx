interface Props {
  questions: string[];
  loading?: boolean;
  onPick: (question: string) => void;
  disabled?: boolean;
}

/** Clickable example-question chips shown while the thread is still empty. */
export default function SuggestedQuestions({ questions, loading, onPick, disabled }: Props) {
  if (loading) {
    return <p className="muted">Loading example questions…</p>;
  }
  if (questions.length === 0) return null;
  return (
    <div className="chip-row" aria-label="Example questions">
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
