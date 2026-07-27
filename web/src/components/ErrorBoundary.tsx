import React from "react";
import Button from "./Button";

interface Props { children: React.ReactNode; }
interface State { hasError: boolean; error: Error | null; }

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "var(--space-xl)", textAlign: "center" }}>
          <div style={{ fontSize: "3rem", marginBottom: "var(--space-md)" }}>⚠</div>
          <h2 style={{ color: "var(--color-danger-dark)" }}>Something went wrong</h2>
          <p style={{ color: "var(--color-text-secondary)", margin: "var(--space-sm) 0 var(--space-lg)" }}>
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <Button variant="primary" onClick={this.handleRetry}>Try Again</Button>
        </div>
      );
    }
    return this.props.children;
  }
}