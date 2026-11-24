import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import BookingForm from '../components/BookingForm';
import api from '../config/api.config';

jest.mock('../config/api.config', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

jest.mock('../components/SeatMap', () => ({ onConfirm }) => (
  <button onClick={() => onConfirm([{ id: 42, seat_number: '3B', seat_class: 'economy', price: 300 }])}>
    Mock-select-seat-3B
  </button>
));

const FLIGHT = {
  id: 1, flight_number: 'MS777', from_airport: 'CAI', to_airport: 'JFK',
  departure_time: '2026-08-01T10:00:00', arrival_time: '2026-08-01T14:00:00',
  aircraft_id: 'B777', status: 'scheduled',
};

const renderAtBookingRoute = () =>
  render(
    <MemoryRouter initialEntries={['/book/1']}>
      <Routes>
        <Route path="/book/:flightId" element={<BookingForm />} />
        <Route path="/dashboard" element={<div>Dashboard Page</div>} />
        <Route path="/flights" element={<div>Flights Page</div>} />
      </Routes>
    </MemoryRouter>
  );

describe('BookingForm Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    api.get.mockImplementation((url) => {
      if (url.startsWith('/flights/')) return Promise.resolve({ data: FLIGHT });
      if (url === '/passenger/profile') return Promise.resolve({ data: { email: 'pax@example.com' } });
      return Promise.resolve({ data: {} });
    });
  });

  test('shows a not-bookable message for a landed flight', async () => {
    api.get.mockImplementation((url) => {
      if (url.startsWith('/flights/')) return Promise.resolve({ data: { ...FLIGHT, status: 'landed' } });
      return Promise.resolve({ data: {} });
    });
    renderAtBookingRoute();
    await waitFor(() => expect(screen.getByText(/can no longer be booked/i)).toBeInTheDocument());
  });

  test('moves to the review step once a seat is selected', async () => {
    renderAtBookingRoute();
    await waitFor(() => screen.getByText('Mock-select-seat-3B'));
    fireEvent.click(screen.getByText('Mock-select-seat-3B'));
    await waitFor(() => expect(screen.getByText('Review & pay')).toBeInTheDocument());
    expect(screen.getByText(/3B \(economy\)/)).toBeInTheDocument();
    expect(screen.getByText('Total: $300.00')).toBeInTheDocument();
  });

  test('confirm button is disabled until terms are accepted', async () => {
    renderAtBookingRoute();
    fireEvent.click(await screen.findByText('Mock-select-seat-3B'));
    await screen.findByText('Review & pay');
    fireEvent.change(screen.getByLabelText(/card number/i), { target: { value: '4111111111111111' } });
    expect(screen.getByRole('button', { name: /confirm booking/i })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('button', { name: /confirm booking/i })).toBeEnabled();
  });

  test('successful confirm shows the booking-confirmed modal', async () => {
    api.post.mockImplementation((url) => {
      if (url === '/booking/create') return Promise.resolve({ data: { id: 99 } });
      if (url === '/payment/process') return Promise.resolve({ data: { amount: 300 } });
      return Promise.resolve({ data: {} });
    });
    renderAtBookingRoute();
    fireEvent.click(await screen.findByText('Mock-select-seat-3B'));
    await screen.findByText('Review & pay');
    fireEvent.change(screen.getByLabelText(/card number/i), { target: { value: '4111111111111111' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /confirm booking/i }));
    await waitFor(() => expect(screen.getByText('Booking confirmed')).toBeInTheDocument());
    expect(screen.getByText(/Booking #99/)).toBeInTheDocument();
  });

  test('a 409 seat-conflict sends the user back to seat selection with an error', async () => {
    api.post.mockRejectedValue({ response: { status: 409 } });
    renderAtBookingRoute();
    fireEvent.click(await screen.findByText('Mock-select-seat-3B'));
    await screen.findByText('Review & pay');
    fireEvent.change(screen.getByLabelText(/card number/i), { target: { value: '4111111111111111' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /confirm booking/i }));
    await waitFor(() => expect(screen.getByText('Mock-select-seat-3B')).toBeInTheDocument());
  });

  test('"Back to seat map" returns to the seat selection step', async () => {
    renderAtBookingRoute();
    fireEvent.click(await screen.findByText('Mock-select-seat-3B'));
    await screen.findByText('Review & pay');
    fireEvent.click(screen.getByRole('button', { name: /back to seat map/i }));
    await waitFor(() => expect(screen.getByText('Mock-select-seat-3B')).toBeInTheDocument());
  });
});
