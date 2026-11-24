import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ProtectedRoute from '../components/ProtectedRoute';

// Minimal unsigned JWT-shaped tokens for decoding (jwt-decode only reads the payload, no verification)
function makeToken(payload) {
  const b64 = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
  return `${b64({ alg: 'none' })}.${b64(payload)}.sig`;
}

const renderWithRoute = (initialPath = '/protected') =>
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/protected" element={<ProtectedRoute allowedRoles={['passenger']}><div>Secret Content</div></ProtectedRoute>} />
        <Route path="/login" element={<div>Login Page</div>} />
        <Route path="/unauthorized" element={<div>Unauthorized Page</div>} />
      </Routes>
    </MemoryRouter>
  );

describe('ProtectedRoute', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('redirects to login when no token present', () => {
    renderWithRoute();
    expect(screen.getByText('Login Page')).toBeInTheDocument();
  });

  test('redirects to login when token is expired', () => {
    localStorage.setItem('access_token', makeToken({ role: 'passenger', exp: Math.floor(Date.now() / 1000) - 100 }));
    renderWithRoute();
    expect(screen.getByText('Login Page')).toBeInTheDocument();
  });

  test('redirects to unauthorized when role does not match', () => {
    localStorage.setItem('access_token', makeToken({ role: 'admin', exp: Math.floor(Date.now() / 1000) + 3600 }));
    renderWithRoute();
    expect(screen.getByText('Unauthorized Page')).toBeInTheDocument();
  });

  test('renders children when token is valid and role matches', () => {
    localStorage.setItem('access_token', makeToken({ role: 'passenger', exp: Math.floor(Date.now() / 1000) + 3600 }));
    renderWithRoute();
    expect(screen.getByText('Secret Content')).toBeInTheDocument();
  });

  test('redirects to login when token is malformed', () => {
    localStorage.setItem('access_token', 'not-a-real-token');
    renderWithRoute();
    expect(screen.getByText('Login Page')).toBeInTheDocument();
  });
});
