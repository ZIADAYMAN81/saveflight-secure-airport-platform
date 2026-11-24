import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../config/api.config';
import { validators, validateInput } from '../utils/validators';
import Logo from './Logo';

const Register = () => {
  const [form, setForm] = useState({ email: '', password: '', fullName: '', passportNumber: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');

    try {
      validateInput(
        { email: form.email, password: form.password, fullName: form.fullName, passportNumber: form.passportNumber.toUpperCase() },
        {
          email: validators.email,
          password: validators.password,
          fullName: validators.fullName,
          passportNumber: validators.passport,
        }
      );
    } catch (err) {
      setError('Please check that all fields are valid (password needs upper/lowercase, a number, and a symbol; passport is 6-9 letters/numbers).');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/register', {
        email: form.email.toLowerCase(),
        password: form.password,
        full_name: form.fullName,
        passport_number: form.passportNumber.toUpperCase(),
      });
      setSuccess(true);
      setTimeout(() => navigate('/login'), 1500);
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
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
          <h1>Join the passenger portal</h1>
          <p>
            Book flights, check in online, and download a secure boarding pass -
            your passport number and personal details are encrypted the moment you submit them.
          </p>
          <div className="hero-stats">
            <div><strong>1</strong><span>Minute sign-up</span></div>
            <div><strong>0</strong><span>Cards stored</span></div>
            <div><strong>24/7</strong><span>Self check-in</span></div>
          </div>
        </div>
      </div>
      <div className="auth-panel">
        <div className="login-container">
          {success ? (
            <>
              <h2>Account created</h2>
              <p className="login-subtext">Redirecting you to login...</p>
            </>
          ) : (
            <>
              <h2>Create passenger account</h2>
              <p className="login-subtext">Free to join. Takes about a minute.</p>
              <form onSubmit={handleSubmit}>
                <label htmlFor="fullName">Full name</label>
                <input id="fullName" value={form.fullName} onChange={update('fullName')} required />

                <label htmlFor="email">Email</label>
                <input id="email" type="email" value={form.email} onChange={update('email')} required autoComplete="username" />

                <label htmlFor="password">Password</label>
                <input id="password" type="password" value={form.password} onChange={update('password')} required autoComplete="new-password" />
                <small>At least 8 characters with uppercase, lowercase, number, and special character</small>

                <label htmlFor="passportNumber">Passport number</label>
                <input id="passportNumber" value={form.passportNumber} onChange={update('passportNumber')} required maxLength={9} />

                {error && <div className="error" role="alert">{error}</div>}
                <button type="submit" disabled={loading}>{loading ? 'Creating account...' : 'Create Account'}</button>
              </form>
              <p>
                Already have an account? <Link to="/login">Sign in</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Register;
