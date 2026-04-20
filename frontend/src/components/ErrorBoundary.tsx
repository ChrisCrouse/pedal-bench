import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
  info: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[pedal-bench] uncaught error:", error, info);
    this.setState({ info });
  }

  reset = () => this.setState({ error: null, info: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-2xl px-6 py-16">
        <div className="rounded-lg border border-red-300 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
          <h2 className="text-lg font-semibold text-red-800 dark:text-red-300">
            Something went wrong
          </h2>
          <p className="mt-2 text-sm text-red-700 dark:text-red-300">
            The app hit an uncaught error. Your data is safe — this is a bug in
            the UI code. Reload to continue, or{" "}
            <button
              onClick={this.reset}
              className="underline hover:text-red-800"
            >
              retry without reloading
            </button>
            .
          </p>
          <details className="mt-4 text-xs">
            <summary className="cursor-pointer select-none font-semibold">
              Technical details
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded bg-white/80 p-3 font-mono text-[11px] text-red-900 dark:bg-zinc-900 dark:text-red-300">
              {this.state.error.stack ?? String(this.state.error)}
            </pre>
          </details>
        </div>
      </div>
    );
  }
}
