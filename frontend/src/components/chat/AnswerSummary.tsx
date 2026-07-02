interface Props {
  summary: string | null;
  loading?: boolean;
}

/** One-line natural-language answer shown above the results table. */
export default function AnswerSummary({ summary, loading }: Props) {
  if (loading) {
    return <p className="summary-callout summary-callout--loading">Summarizing…</p>;
  }
  if (!summary) return null;
  return <p className="summary-callout">{summary}</p>;
}
