import React, { useMemo, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { jwtDecode } from 'jwt-decode';
import Logo from './Logo';

const STAFF_ROLES = ['agent', 'crew', 'security', 'admin'];

const NAV_ITEMS_BY_ROLE = {
  passenger: [
    { to: '/dashboard', label: 'My Bookings', short: 'Bookings' },
    { to: '/flights', label: 'Search Flights', short: 'Search' },
  ],
  staff: [
    { to: '/staff/dashboard', label: 'Staff Dashboard', short: 'Staff' },
  ],
  admin: [
    { to: '/admin', label: 'Admin Panel', short: 'Admin' },
    { to: '/admin/analytics', label: 'Analytics', short: 'Analytics' },
  ],
};

const Layout = ({ children }) => {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const role = useMemo(() => {
    const token = localStorage.getItem('access_token');
    if (!token) return null;
    try {
      return jwtDecode(token).role;
    } catch {
      return null;
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    navigate('/login', { replace: true });
  };

  const isStaff = STAFF_ROLES.includes(role);
  const navItems = [
    ...(role === 'passenger' ? NAV_ITEMS_BY_ROLE.passenger : []),
    ...(isStaff ? NAV_ITEMS_BY_ROLE.staff : []),
    ...(role === 'admin' ? NAV_ITEMS_BY_ROLE.admin : []),
  ];

  return (
    <div className="app-shell">
      <header className="topnav">
        <div className="brand">
          <span className="brand-mark"><Logo size={18} /></span>
          Save<span className="brand-accent">Flight</span>
        </div>

        <nav className="nav-links nav-links-desktop" aria-label="Primary">
          {navItems.map((item) => <NavLink key={item.to} to={item.to}>{item.label}</NavLink>)}
        </nav>

        <div className="nav-right">
          {role && <span className="role-chip nav-right-chip">{role}</span>}
          <button type="button" className="logout-btn nav-right-logout" onClick={handleLogout}>Log out</button>
          <button
            type="button"
            className="hamburger-btn"
            aria-label="Toggle menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </header>

      {menuOpen && (
        <div className="mobile-menu" role="navigation" aria-label="Mobile">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} onClick={() => setMenuOpen(false)}>{item.label}</NavLink>
          ))}
          <button type="button" className="logout-btn" onClick={handleLogout}>Log out ({role})</button>
        </div>
      )}

      <main className="app-content">{children}</main>

      {navItems.length > 0 && (
        <nav className="bottom-nav" aria-label="Primary (mobile)">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className="bottom-nav-item">
              {item.short}
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  );
};

export default Layout;
