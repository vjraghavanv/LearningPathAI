import { NavLink } from "react-router-dom";
import "./Sidebar.css";

interface NavItem {
  to: string;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/",          label: "Dashboard",    icon: "📊" },
  { to: "/resources", label: "Resources",    icon: "📚" },
  { to: "/plan",      label: "Learning Plan",icon: "🗓️" },
  { to: "/career",    label: "Career Goal",  icon: "🎯" },
  { to: "/search",    label: "Search",       icon: "🔍" },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="sidebar-overlay"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <nav
        className={`sidebar${isOpen ? " sidebar--open" : ""}`}
        aria-label="Main navigation"
      >
        <div className="sidebar__header">
          <span className="sidebar__logo" aria-label="LearningPath AI">
            🧠 LearningPath AI
          </span>
        </div>

        <ul className="sidebar__nav" role="list">
          {NAV_ITEMS.map(({ to, label, icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `sidebar__link${isActive ? " sidebar__link--active" : ""}`
                }
                onClick={onClose}
              >
                <span className="sidebar__icon" aria-hidden="true">{icon}</span>
                <span className="sidebar__label">{label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </>
  );
}
