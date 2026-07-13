import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { ThemeToggle } from "./ThemeToggle";
import "./Layout.css";

export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="layout">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="layout__body">
        {/* Top bar — visible on mobile and tablet */}
        <header className="layout__topbar">
          <button
            className="layout__menu-btn"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={sidebarOpen}
          >
            ☰
          </button>
          <span className="layout__topbar-title">LearningPath AI</span>
          <ThemeToggle />
        </header>

        {/* Desktop top-right theme toggle */}
        <div className="layout__desktop-actions">
          <ThemeToggle />
        </div>

        <main className="layout__main" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
