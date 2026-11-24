import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import FlightSearch from '../components/FlightSearch';
import api from '../config/api.config';

jest.mock('../config/api.config', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const FLIGHTS = [
  {
    id: 1, flight_number: 'MS777', departure_time: '2026-08-01T10:00:00', arrival_time: '2026-08-01T14:00:00',
    from_airport: 'CAI', to_airport: 'JFK', gate: 'A1', terminal: '1', aircraft_id: 'B777',
    base_price: 500, status: 'scheduled', available_seats: 120,
  },
  {
    id: 2, flight_number: 'BA200', departure_time: '2026-08-01T08:00:00', arrival_time: '2026-08-01T11:00:00',
    from_airport: 'CAI', to_airport: 'JFK', gate: 'B2', terminal: '2', aircraft_id: 'A320',
    base_price: 300, status: 'landed', available_seats: 50,
  },
  {
    id: 3, flight_number: 'EK300', departure_time: '2026-08-01T12:00:00', arrival_time: '2026-08-01T15:00:00',
    from_airport: 'CAI', to_airport: 'JFK', gate: 'C3', terminal: '3', aircraft_id: 'A380',
    base_price: 400, status: 'scheduled', available_seats: 0,
  },
];

describe('FlightSearch Component', () => {
  beforeEach(() => jest.clearAllMocks());

  test('renders the search form fields', () => {
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    expect(screen.getByLabelText(/from/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^to$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/departure date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/passengers/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument();
  });

  test('searching calls the flights API and renders results', async () => {
    api.get.mockResolvedValue({ data: FLIGHTS });
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => expect(screen.getByText('MS777')).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith('/flights', { params: {} });
    expect(screen.getByText('BA200')).toBeInTheDocument();
    expect(screen.getByText('EK300')).toBeInTheDocument();
  });

  test('search passes selected airport/date filters as query params', async () => {
    api.get.mockResolvedValue({ data: [] });
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText(/from/i), { target: { value: 'CAI' } });
    fireEvent.change(screen.getByLabelText(/^to$/i), { target: { value: 'JFK' } });
    fireEvent.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/flights', { params: { from_airport: 'CAI', to_airport: 'JFK' } }));
  });

  test('shows a message when no flights match', async () => {
    api.get.mockResolvedValue({ data: [] });
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => expect(screen.getByText(/no flights match your search/i)).toBeInTheDocument());
  });

  test('sold-out flights show a disabled "Sold out" button', async () => {
    api.get.mockResolvedValue({ data: FLIGHTS });
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => screen.getByText('EK300'));
    expect(screen.getByRole('button', { name: /sold out/i })).toBeDisabled();
  });

  test('already-landed flights show a disabled "Not bookable" button', async () => {
    api.get.mockResolvedValue({ data: FLIGHTS });
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => screen.getByText('BA200'));
    expect(screen.getByRole('button', { name: /not bookable/i })).toBeDisabled();
  });

  test('a bookable flight with open seats shows an enabled "Select Flight" button', async () => {
    api.get.mockResolvedValue({ data: FLIGHTS });
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => screen.getByText('MS777'));
    expect(screen.getByRole('button', { name: /^select flight$/i })).toBeEnabled();
  });

  test('sorting by price reorders the results', async () => {
    api.get.mockResolvedValue({ data: FLIGHTS });
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => screen.getByText('MS777'));
    fireEvent.change(screen.getByLabelText(/sort by/i), { target: { value: 'price' } });
    const flightNumbers = screen.getAllByText(/^(MS777|BA200|EK300)$/).map((el) => el.textContent);
    expect(flightNumbers[0]).toBe('BA200'); // cheapest ($300)
  });

  test('filtering by airline hides non-matching flights', async () => {
    api.get.mockResolvedValue({ data: FLIGHTS });
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => screen.getByText('MS777'));
    fireEvent.change(screen.getByLabelText(/airline/i), { target: { value: 'EK' } });
    expect(screen.queryByText('MS777')).not.toBeInTheDocument();
    expect(screen.getByText('EK300')).toBeInTheDocument();
  });

  test('shows a generic error message when the search request fails', async () => {
    api.get.mockRejectedValue(new Error('network error'));
    render(<MemoryRouter><FlightSearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => expect(screen.getByText(/unable to search flights/i)).toBeInTheDocument());
  });
});
