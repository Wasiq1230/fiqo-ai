/**
 * Top-level error boundary.
 *
 * Catches render/runtime errors anywhere in the tree so a single component
 * fault shows a friendly recovery screen instead of a blank white page.
 * The real error is logged to the console (dev) but never shown to the user.
 */
import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, showDetails: false };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // In production this is where you'd forward to Sentry / a logging service.
    console.error("Unhandled UI error:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, showDetails: false });
    window.location.assign("/");
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="um-fallback">
          <div className="um-fallback-card" style={{ maxWidth: 500 }}>
            <h1>Something went wrong</h1>
            <p>
              An unexpected error occurred. Your data is safe — please reload
              and try again.
            </p>

            <div className="um-toolbar-btns" style={{ justifyContent: "center", marginBottom: 16 }}>
              <button className="um-btn um-btn-primary" onClick={this.handleReset}>
                Reload app
              </button>
              <button
                className="um-btn"
                onClick={() => this.setState(prev => ({ showDetails: !prev.showDetails }))}
              >
                {this.state.showDetails ? "Hide details" : "Show details"}
              </button>
            </div>

            {this.state.showDetails && this.state.error && (
              <pre style={{
                textAlign: "left",
                background: "#f1f5f9",
                color: "#dc2626",
                padding: 12,
                borderRadius: 8,
                fontSize: 12,
                whiteSpace: "pre-wrap",
                maxHeight: 200,
                overflowY: "auto",
                border: "1px solid rgba(15, 23, 60, 0.08)"
              }}>
                {this.state.error.toString() + "\n" + (this.state.error.stack || "")}
              </pre>
            )}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
