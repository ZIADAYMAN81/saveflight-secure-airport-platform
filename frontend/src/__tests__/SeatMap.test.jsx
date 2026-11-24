import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SeatMap from '../components/SeatMap';
import api from '../config/api.config';

jest.mock('../config/api.config', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const SAMPLE_SEATS = {
  flight_id: 1,
  flight_number: 'TS100',
  aircraft_id: 'A320',
  seats: [
    { id: 1, seat_number: '1A', seat_class: 'first', position: 'window', is_exit_row: false, price: 600, status: 'available' },
    { id: 2, seat_number: '1B', seat_class: 'first', position: 'middle', is_exit_row: false, price: 600, status: 'occupied' },
    { id: 3, seat_number: '1C', seat_class: 'first', position: 'aisle', is_exit_row: false, price: 600, status: 'available' },
    { id: 4, seat_number: '1D', seat_class: 'first', position: 'aisle', is_exit_row: false, price: 600, status: 'available' },
    { id: 5, seat_number: '1E', seat_class: 'first', position: 'middle', is_exit_row: false, price: 600, status: 'available' },
    { id: 6, seat_number: '1F', seat_class: 'first', position: 'window', is_exit_row: false, price: 600, status: 'restricted' },
  ],
  class_legend: { first: { rows: '1-4', multiplier: 3.0 } },
};

describe('SeatMap Component', () => {
  beforeEach(() => jest.clearAllMocks());

  test('shows loading state before data arrives', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    render(<SeatMap flightId={1} onConfirm={jest.fn()} />);
    expect(screen.getByText(/loading seat map/i)).toBeInTheDocument();
  });

  test('renders the legend and all seats once loaded', async () => {
    api.get.mockResolvedValue({ data: SAMPLE_SEATS });
    render(<SeatMap flightId={1} onConfirm={jest.fn()} />);
    await waitFor(() => expect(screen.getByText('Available')).toBeInTheDocument());
    expect(screen.getByText('Occupied')).toBeInTheDocument();
    expect(screen.getByText('Selected')).toBeInTheDocument();
    expect(screen.getByText('Restricted')).toBeInTheDocument();
  });

  test('shows an error message if the seat map fails to load', async () => {
    api.get.mockRejectedValue(new Error('network error'));
    render(<SeatMap flightId={1} onConfirm={jest.fn()} />);
    await waitFor(() => expect(screen.getByText(/unable to load seat map/i)).toBeInTheDocument());
  });

  test('occupied and restricted seats are disabled', async () => {
    api.get.mockResolvedValue({ data: SAMPLE_SEATS });
    render(<SeatMap flightId={1} onConfirm={jest.fn()} />);
    await waitFor(() => screen.getByTitle(/1A/));
    expect(screen.getByTitle(/Already booked/i)).toBeDisabled();
    expect(screen.getByTitle(/Restricted/i)).toBeDisabled();
  });

  test('clicking an available seat opens the detail popup with price', async () => {
    api.get.mockResolvedValue({ data: SAMPLE_SEATS });
    render(<SeatMap flightId={1} onConfirm={jest.fn()} />);
    await waitFor(() => screen.getByTitle(/1A - First Class/));
    fireEvent.click(screen.getByTitle(/1A - First Class/));
    expect(screen.getByText('Seat 1A')).toBeInTheDocument();
    expect(screen.getByText('$600.00')).toBeInTheDocument();
  });

  test('adding a seat moves it into the selected-seats cart with running total', async () => {
    api.get.mockResolvedValue({ data: SAMPLE_SEATS });
    render(<SeatMap flightId={1} onConfirm={jest.fn()} />);
    await waitFor(() => screen.getByTitle(/1A - First Class/));
    fireEvent.click(screen.getByTitle(/1A - First Class/));
    fireEvent.click(screen.getByRole('button', { name: /add seat/i }));
    expect(screen.getByText(/Selected seats \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText('Total: $600.00')).toBeInTheDocument();
  });

  test('removing a selected seat updates the total', async () => {
    api.get.mockResolvedValue({ data: SAMPLE_SEATS });
    render(<SeatMap flightId={1} onConfirm={jest.fn()} />);
    await waitFor(() => screen.getByTitle(/1A - First Class/));
    fireEvent.click(screen.getByTitle(/1A - First Class/));
    fireEvent.click(screen.getByRole('button', { name: /add seat/i }));
    fireEvent.click(screen.getByRole('button', { name: /remove/i }));
    expect(screen.queryByText(/Selected seats/i)).not.toBeInTheDocument();
  });

  test('calls onConfirm with the selected seats when continuing', async () => {
    const onConfirm = jest.fn();
    api.get.mockResolvedValue({ data: SAMPLE_SEATS });
    render(<SeatMap flightId={1} onConfirm={onConfirm} />);
    await waitFor(() => screen.getByTitle(/1A - First Class/));
    fireEvent.click(screen.getByTitle(/1A - First Class/));
    fireEvent.click(screen.getByRole('button', { name: /add seat/i }));
    fireEvent.click(screen.getByRole('button', { name: /continue to booking/i }));
    expect(onConfirm).toHaveBeenCalledWith([expect.objectContaining({ seat_number: '1A' })]);
  });

  test('closing the popup without adding does not select the seat', async () => {
    api.get.mockResolvedValue({ data: SAMPLE_SEATS });
    render(<SeatMap flightId={1} onConfirm={jest.fn()} />);
    await waitFor(() => screen.getByTitle(/1A - First Class/));
    fireEvent.click(screen.getByTitle(/1A - First Class/));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByText(/Selected seats/i)).not.toBeInTheDocument();
  });

  test('exit row seats show the exit-row marker class', async () => {
    const withExitRow = {
      ...SAMPLE_SEATS,
      seats: [{ ...SAMPLE_SEATS.seats[0], is_exit_row: true }, ...SAMPLE_SEATS.seats.slice(1)],
    };
    api.get.mockResolvedValue({ data: withExitRow });
    render(<SeatMap flightId={1} onConfirm={jest.fn()} />);
    await waitFor(() => screen.getByTitle(/1A - First Class/));
    expect(screen.getByTitle(/1A - First Class/)).toHaveClass('seat-exit-row');
  });
});
