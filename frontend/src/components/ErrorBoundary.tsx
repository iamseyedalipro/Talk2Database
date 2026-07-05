import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Optional custom fallback; defaults to a friendly error card. */
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render/lifecycle errors in the subtree so a single broken component
 * shows a recoverable error card instead of unmounting the whole app (which
 * would leave the user staring at a blank page).
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface the failure for debugging without crashing the app.
    console.error('Unhandled UI error:', error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render(): ReactNode {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="page">
          <div className="card">
            <h2 className="page__title">Something went wrong</h2>
            <p className="muted">
              This page hit an unexpected error and couldn&apos;t render. You can try again, or
              reload the app.
            </p>
            <div className="banner banner--error" role="alert">
              {this.state.error.message}
            </div>
            <div className="page__header">
              <button type="button" className="btn btn--primary" onClick={this.reset}>
                Try again
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => window.location.reload()}
              >
                Reload
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
