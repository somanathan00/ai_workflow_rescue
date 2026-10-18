import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";

const link = ({ isActive }: { isActive: boolean }) => (isActive ? "nav-link active" : "nav-link");

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">✓</span>
          <div>
            <strong>Workflow Rescue</strong>
            <small>AI-assisted recovery</small>
          </div>
        </div>

        <nav className="nav">
          <NavLink to="/" end className={link}>
            Dashboard
          </NavLink>
          <NavLink to="/orders" className={link}>
            Orders
          </NavLink>
          <NavLink to="/workflows" className={link}>
            Workflows
          </NavLink>
          {user?.role === "admin" && (
            <NavLink to="/approvals" className={link}>
              Approvals
            </NavLink>
          )}
          {user?.role === "admin" && (
            <NavLink to="/ai-quality" className={link}>
              AI quality
            </NavLink>
          )}
          <NavLink to="/system" className={link}>
            System
          </NavLink>
        </nav>

        <div className="sidebar-foot">
          <div className="whoami">
            <span className="avatar">{user?.username.slice(0, 1).toUpperCase()}</span>
            <div>
              <strong>{user?.username}</strong>
              <small className={`role role-${user?.role}`}>{user?.role}</small>
            </div>
          </div>
          <button className="btn btn-ghost btn-block" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
