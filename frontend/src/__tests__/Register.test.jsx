import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Register from '../components/Register';
import api from '../config/api.config';

jest.mock('../config/api.config', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

const fillForm = (overrides = {}) => {
  const values = {
    fullName: 'Jane Traveler',
    email: 'jane@example.com',
    password: 'SecureP@ss1!',
    passportNumber: 'AB123456',
    ...overrides,
  };
  fireEvent.change(screen.getByLabelText(/Full name/i), { target: { value: values.fullName } });
  fireEvent.change(screen.getByLabelText(/^Email/i), { target: { value: values.email } });
  fireEvent.change(screen.getByLabelText(/^Password/i), { target: { value: values.password } });
  fireEvent.change(screen.getByLabelText(/Passport number/i), { target: { value: values.passportNumber } });
};

describe('Register Component', () => {
  beforeEach(() => jest.clearAllMocks());

  test('renders all required fields', () => {
    render(<MemoryRouter><Register /></MemoryRouter>);
    expect(screen.getByLabelText(/Full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Passport number/i)).toBeInTheDocument();
  });

  test('rejects an invalid passport number client-side', async () => {
    render(<MemoryRouter><Register /></MemoryRouter>);
    fillForm({ passportNumber: 'bad' });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    await waitFor(() => expect(screen.getByText(/please check that all fields are valid/i)).toBeInTheDocument());
    expect(api.post).not.toHaveBeenCalled();
  });

  test('submits valid registration and shows success', async () => {
    api.post.mockResolvedValue({ data: { id: 1, email: 'jane@example.com', role: 'passenger' } });
    render(<MemoryRouter><Register /></MemoryRouter>);
    fillForm();
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    await waitFor(() => expect(screen.getByText(/account created/i)).toBeInTheDocument());
    expect(api.post).toHaveBeenCalledWith('/auth/register', expect.objectContaining({ email: 'jane@example.com' }));
  });

  test('shows server error message on failed registration', async () => {
    api.post.mockRejectedValue({ response: { data: { detail: 'Unable to register with the provided details' } } });
    render(<MemoryRouter><Register /></MemoryRouter>);
    fillForm();
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    await waitFor(() => expect(screen.getByText(/unable to register/i)).toBeInTheDocument());
  });
});
