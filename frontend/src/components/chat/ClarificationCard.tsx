import type { AskResponse } from '../../api/types';

interface Props {
  ask: AskResponse;
  /** Called with the chosen interpretation's full question text. */
  onPick: (question: string) => void;
  disabled?: boolean;
}

/**
 * Rendered when the model could not map the question onto the schema.
 * Shows the clarifying question with one button per suggested interpretation;
 * clicking one re-asks with that complete question.
 */
export default function ClarificationCard({ ask, onPick, disabled }: Props) {
  const isUnanswerable = ask.status === 'unanswerable';
  return (
    <div className="clarification-card">
      <p className="clarification-card__question">
        {isUnanswerable
          ? ask.explanation ?? 'This question cannot be answered from the connected database.'
          : ask.clarification_question}
      </p>
      {ask.suggested_interpretations.length > 0 && (
        <div className="clarification-card__options">
          {ask.suggested_interpretations.map((option) => (
            <button
              key={option.description}
              type="button"
              className="btn btn--secondary clarification-card__option"
              onClick={() => onPick(option.description)}
              disabled={disabled}
            >
              <span className="clarification-card__label">{option.label}</span>
              <span className="clarification-card__description">{option.description}</span>
            </button>
          ))}
        </div>
      )}
      {!isUnanswerable && (
        <p className="muted clarification-card__hint">
          Pick an option above, or rephrase your question below.
        </p>
      )}
    </div>
  );
}
