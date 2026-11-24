import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../config/api.config';
import { validators } from '../utils/validators';
import Logo from './Logo';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');

    if (!validators.email(email)) {
      setError('Enter a valid email address');
      return;
    }
    if (!password) {
      setError('Enter your password');
      return;
    }

    setLoading(true);
    try {
      const response = await api.post('/auth/login', { email, password });
      const { access_token, requires_2fa, user_id } = response.data;

      if (requires_2fa) {
        navigate('/2fa-verify', { state: { userId: user_id } });
        return;
      }

      localStorage.setItem('access_token', access_token);
      navigate('/dashboard');
    } catch (err) {
      if (err.response?.status === 423) {
        setError('Account temporarily locked due to repeated failed login attempts. Try again later.');
      } else if (err.response?.status === 429) {
        setError('Too many login attempts. Please wait a minute and try again.');
      } else if (err.response?.status === 403) {
        setError('2FA enrollment is required for this account. Contact an administrator.');
      } else {
        setError(err.response?.data?.detail || 'Invalid email or password');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-hero">
        <div className="auth-hero-content">
          <div className="brand">
            <span className="brand-mark"><Logo /></span>
            Save<span className="brand-accent">Flight</span>
          </div>
          <h1>Book smarter. Fly secure.</h1>
          <p>
            One login for passenger check-in, gate operations, and airport security -
            protected by encryption, role-based access, and mandatory 2FA for staff.
          </p>
          <div className="hero-stats">
            <div><strong>AES-256</strong><span>Data at rest</span></div>
            <div><strong>5 roles</strong><span>Access control</span></div>
            <div><strong>2FA</strong><span>Staff accounts</span></div>
          </div>
        </div>
      </div>
      <div className="auth-panel">
        <div className="login-container">
          <h2>Welcome back</h2>
          <p className="login-subtext">Sign in to manage your flights and bookings.</p>
          <form onSubmit={handleSubmit}>
            <label htmlFor="email">Email</label>
            <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" />
            <label htmlFor="password">Password</label>
            <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
            {error && <div className="error" role="alert">{error}</div>}
            <button type="submit" disabled={loading}>{loading ? 'Signing in...' : 'Sign In'}</button>
          </form>
          <p>
            New passenger? <Link to="/register">Create an account</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
