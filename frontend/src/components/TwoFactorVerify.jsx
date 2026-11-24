import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import api from '../config/api.config';
import { validators } from '../utils/validators';
import Logo from './Logo';

const TwoFactorVerify = () => {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const userId = location.state?.userId;

  if (!userId) {
    navigate('/login', { replace: true });
    return null;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');

    if (!validators.totpCode(code)) {
      setError('Enter the 6-digit code from your authenticator app');
      return;
    }

    setLoading(true);
    try {
      const response = await api.post('/auth/2fa-verify', { user_id: userId, totp_code: code });
      localStorage.setItem('access_token', response.data.access_token);
      navigate('/staff/dashboard');
    } catch (err) {
      if (err.response?.status === 423) {
        setError('Account locked due to repeated failed attempts.');
      } else if (err.response?.status === 429) {
        setError('Too many attempts. Please wait and try again.');
      } else {
        setError('Invalid verification code');
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
          <h1>Staff verification</h1>
          <p>
            Staff and admin accounts require a second factor on every login -
            enter the current code from your authenticator app, or the code
            we just emailed to your account's address.
          </p>
        </div>
      </div>
      <div className="auth-panel">
        <div className="login-container">
          <h2>Two-factor verification</h2>
          <p className="login-subtext">Enter the code from your authenticator app, or from your email.</p>
          <form onSubmit={handleSubmit}>
            <label htmlFor="totp">Verification code</label>
            <input
              id="totp"
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              autoFocus
              required
            />
            {error && <div className="error" role="alert">{error}</div>}
            <button type="submit" disabled={loading}>{loading ? 'Verifying...' : 'Verify'}</button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default TwoFactorVerify;
