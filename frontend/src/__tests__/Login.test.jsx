import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Login from '../components/Login';
import api from '../config/api.config';

jest.mock('../config/api.config', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

describe('Login Component', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  test('renders login form', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  test('shows validation error for invalid email', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'bad' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'StrongPass1!' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(screen.getByText(/Enter a valid email address/i)).toBeInTheDocument();
  });

  test('stores token and redirects on successful login without 2FA', async () => {
    api.post.mockResolvedValue({ data: { access_token: 'abc123', requires_2fa: false } });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'pax@example.com' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'StrongPass1!' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(localStorage.getItem('access_token')).toBe('abc123'));
  });

  test('shows generic error message on invalid credentials', async () => {
    api.post.mockRejectedValue({ response: { status: 401, data: { detail: 'Invalid credentials' } } });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'pax@example.com' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'WrongPass1!' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText(/Invalid credentials/i)).toBeInTheDocument());
  });

  test('shows lockout message on 423 response', async () => {
    api.post.mockRejectedValue({ response: { status: 423 } });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'pax@example.com' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'WrongPass1!' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText(/temporarily locked/i)).toBeInTheDocument());
  });

  test('shows rate limit message on 429 response', async () => {
    api.post.mockRejectedValue({ response: { status: 429 } });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'pax@example.com' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'WrongPass1!' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(screen.getByText(/too many login attempts/i)).toBeInTheDocument());
  });

  test('renders link to registration page', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    expect(screen.getByText(/create an account/i)).toBeInTheDocument();
  });
});
