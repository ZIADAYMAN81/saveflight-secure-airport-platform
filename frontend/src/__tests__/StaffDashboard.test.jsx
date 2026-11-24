import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import StaffDashboard from '../components/StaffDashboard';
import api from '../config/api.config';

jest.mock('../config/api.config', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

function makeToken(payload) {
  const b64 = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
  return `${b64({ alg: 'none' })}.${b64(payload)}.sig`;
}

describe('StaffDashboard Component', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
    api.get.mockResolvedValue({ data: { flights_today: 2, checkins_completed: 5, pending_boarding: 1 } });
  });

  test('shows the boarding-pass redemption form for agents', async () => {
    localStorage.setItem('access_token', makeToken({ role: 'agent' }));
    render(<MemoryRouter><StaffDashboard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/Redeem Boarding Pass/i)).toBeInTheDocument());
  });

  test('does not show agent tools for crew role', async () => {
    localStorage.setItem('access_token', makeToken({ role: 'crew' }));
    render(<MemoryRouter><StaffDashboard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/Flight Manifest/i)).toBeInTheDocument());
    expect(screen.queryByText(/Redeem Boarding Pass/i)).not.toBeInTheDocument();
  });

  test('agent can submit a boarding pass token for check-in', async () => {
    localStorage.setItem('access_token', makeToken({ role: 'agent' }));
    api.post.mockResolvedValue({ data: { success: true, message: 'Passenger checked in' } });

    render(<MemoryRouter><StaffDashboard /></MemoryRouter>);
    await waitFor(() => screen.getByPlaceholderText(/Boarding pass token/i));

    fireEvent.change(screen.getByPlaceholderText(/Boarding pass token/i), { target: { value: 'tok_abc' } });
    fireEvent.click(screen.getByRole('button', { name: /check-in passenger/i }));

    await waitFor(() => expect(screen.getByText(/passenger checked in/i)).toBeInTheDocument());
    expect(api.post).toHaveBeenCalledWith('/staff/checkin-passenger', { boarding_pass_token: 'tok_abc' });
  });

  test('shows admin panel link for admin role', async () => {
    localStorage.setItem('access_token', makeToken({ role: 'admin' }));
    render(<MemoryRouter><StaffDashboard /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText(/go to admin panel/i)).toBeInTheDocument());
  });
});
