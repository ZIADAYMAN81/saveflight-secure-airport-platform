import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import api from '../config/api.config';
import SeatMap from './SeatMap';
import { formatDuration, formatTimeUTC } from '../utils/flightHelpers';

const STEP_SEATS = 'seats';
const STEP_REVIEW = 'review';
const STEP_DONE = 'done';
const BOOKABLE_STATUSES = new Set(['scheduled', 'boarding']);

const BookingForm = () => {
  const { flightId } = useParams();
  const navigate = useNavigate();

  const [flight, setFlight] = useState(null);
  const [profile, setProfile] = useState(null);
  const [step, setStep] = useState(STEP_SEATS);
  const [seatMapKey, setSeatMapKey] = useState(0); // bump to force SeatMap to refetch
  const [selectedSeats, setSelectedSeats] = useState([]);
  const [cardNumber, setCardNumber] = useState('');
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [confirmedBookings, setConfirmedBookings] = useState([]);

  useEffect(() => {
    api.get(`/flights/${flightId}`).then((res) => setFlight(res.data)).catch(() => setError('Flight not found'));
    api.get('/passenger/profile').then((res) => setProfile(res.data)).catch(() => {});
  }, [flightId]);

  const handleSeatsConfirmed = (seats) => {
    setSelectedSeats(seats);
    setStep(STEP_REVIEW);
  };

  const backToSeats = () => {
    setError('');
    setSeatMapKey((k) => k + 1); // remount SeatMap so it refetches current availability
    setStep(STEP_SEATS);
  };

  const handleConfirmBooking = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    const created = [];
    try {
      for (const seat of selectedSeats) {
        const bookingRes = await api.post('/booking/create', { flight_id: Number(flightId), seat_id: seat.id });
        await api.post('/payment/process', {
          booking_id: bookingRes.data.id,
          card_number: cardNumber,
          card_expiry: '12/29',
          card_cvc: '123',
        });
        created.push({ ...bookingRes.data, seat_number: seat.seat_number, price: seat.price });
      }
      setConfirmedBookings(created);
      setStep(STEP_DONE);
    } catch (err) {
      if (err.response?.status === 409) {
        setError('One of your selected seats was just booked by someone else. Please choose another seat.');
        backToSeats();
      } else {
        setError(err.response?.data?.detail || 'Booking failed. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (error && !flight) return <div className="error" role="alert">{error}</div>;
  if (!flight) return <div>Loading flight...</div>;
  if (!BOOKABLE_STATUSES.has(flight.status)) {
    return (
      <div className="error" role="alert">
        {flight.flight_number} is {flight.status} and can no longer be booked.{' '}
        <Link to="/flights">Search other flights</Link>
      </div>
    );
  }

  const total = selectedSeats.reduce((sum, s) => sum + s.price, 0);

  return (
    <>
      <div className="page-header">
        <h1>Book {flight.flight_number}</h1>
        <p>{flight.from_airport} to {flight.to_airport} - {formatTimeUTC(flight.departure_time)}</p>
      </div>

      <div className="dashboard">
        <div className="booking-flight-summary">
          <div>
            <strong>{flight.flight_number}</strong>
            <div>{flight.from_airport} &rarr; {flight.to_airport}</div>
          </div>
          <div>
            {formatTimeUTC(flight.departure_time)} - {formatTimeUTC(flight.arrival_time)}
            <div>{formatDuration(flight.departure_time, flight.arrival_time)} - {flight.aircraft_id || 'TBA'}</div>
          </div>
        </div>

        {step === STEP_SEATS && (
          <SeatMap key={seatMapKey} flightId={flightId} onConfirm={handleSeatsConfirmed} />
        )}

        {step === STEP_REVIEW && (
          <form onSubmit={handleConfirmBooking} className="booking-review">
            <h3>Review &amp; pay</h3>

            <section>
              <h4>Passenger</h4>
              {profile ? (
                <p>{profile.email} &middot; account on file (passport already verified at registration)</p>
              ) : (
                <p>Loading passenger details...</p>
              )}
            </section>

            <section>
              <h4>Seats</h4>
              <ul>
                {selectedSeats.map((s) => (
                  <li key={s.id}>{s.seat_number} ({s.seat_class}) - ${s.price.toFixed(2)}</li>
                ))}
              </ul>
              <p className="seat-cart-total">Total: ${total.toFixed(2)}</p>
            </section>

            <section>
              <h4>Payment method</h4>
              <select defaultValue="card" disabled>
                <option value="card">Credit / Debit Card</option>
              </select>
              <label htmlFor="cardNumber">Card number</label>
              <input
                id="cardNumber"
                value={cardNumber}
                onChange={(e) => setCardNumber(e.target.value)}
                placeholder="4111111111111111"
                required
              />
              <small>Your card number is never stored - only a tokenized reference and the last 4 digits.</small>
            </section>

            <label className="checkbox-row">
              <input type="checkbox" checked={agreedToTerms} onChange={(e) => setAgreedToTerms(e.target.checked)} required />
              I agree to the fare rules and terms &amp; conditions.
            </label>

            {error && <div className="error" role="alert">{error}</div>}

            <div className="booking-review-actions">
              <button type="button" className="secondary-btn" onClick={backToSeats}>Back to seat map</button>
              <button type="submit" disabled={submitting || !agreedToTerms}>
                {submitting ? 'Processing...' : `Confirm Booking - $${total.toFixed(2)}`}
              </button>
            </div>
          </form>
        )}

        {step === STEP_DONE && (
          <div className="seat-popup-backdrop">
            <div className="seat-popup booking-confirmation-modal">
              <h4>Booking confirmed</h4>
              <p>Your seat{confirmedBookings.length > 1 ? 's are' : ' is'} booked and paid for.</p>
              <ul>
                {confirmedBookings.map((b) => (
                  <li key={b.id}>Booking #{b.id} - Seat {b.seat_number} - ${b.price.toFixed(2)}</li>
                ))}
              </ul>
              <button type="button" onClick={() => navigate('/dashboard')}>Go to My Bookings</button>
              <Link to="/flights">Search another flight</Link>
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export default BookingForm;
