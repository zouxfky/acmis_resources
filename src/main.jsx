import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

class RootErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("ACMIS frontend crash:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="dashboard-shell">
          <div className="dashboard-frame">
            <section className="workspace-card">
              <div className="notice is-error">
                前端发生错误：{this.state.error.message || "未知错误"}
              </div>
            </section>
          </div>
        </main>
      );
    }

    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </React.StrictMode>
);
