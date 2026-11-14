import { Component, type ReactNode, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

/** Last-resort screen so a bad data file shows a message instead of a blank page. */
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="boot">
        <img src="./emblem.png" alt="" width={72} height={72} />
        <p className="warn">Something went wrong: {this.state.error.message}</p>
        <button
          className="btn btn-primary"
          onClick={() => {
            window.location.hash = "";
            window.location.reload();
          }}
        >
          Reset view
        </button>
      </div>
    );
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
