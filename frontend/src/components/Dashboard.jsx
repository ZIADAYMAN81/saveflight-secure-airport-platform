import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../config/api.config';
import StatusBadge from './StatusBadge';

const Dashboard = () => {
  const [bookings, setBookings] = useState([]);
  const [error, setError] = useState('');
  const [checkinTokens, setCheckinTokens] = useState({});

  const fetchBookings = async () => {
    try {
      const response = await api.get('/passenger/bookings');
      setBookings(response.data);
    } catch (err) {
      setError('Failed to load bookings');
    }
  };

  useEffect(() => {
    fetchBookings();
  }, []);

  const handleCheckin = async (bookingId) => {
    setError('');
    try {
      const response = await api.post('/passenger/checkin', { booking_id: bookingId });
      setCheckinTokens((prev) => ({ ...prev, [bookingId]: response.data.boarding_pass_token }));
      fetchBookings();
    } catch (err) {
      setError(err.response?.data?.detail || 'Check-in failed');
    }
  };

  return (
    <>
      <div className="page-header">
        <h1>My Bookings</h1>
        <p>Check in online and access your boarding pass before you head to the airport.</p>
      </div>
      <div className="dashboard">
        {error && <p className="error" role="alert">{error}</p>}

        {bookings.length === 0 ? (
          <p>No bookings found. <Link to="/flights">Search flights</Link> to book one.</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Booking</th>
                  <th>Flight</th>
                  <th>Seat</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {bookings.map((booking) => (
                  <tr key={booking.id}>
                    <td>#{booking.id}</td>
                    <td>{booking.flight_id}</td>
                    <td>{booking.seat_number || 'Unassigned'}</td>
                    <td><StatusBadge status={booking.status} /></td>
                    <td>
                      {booking.status === 'active' && (
                        <button onClick={() => handleCheckin(booking.id)}>Check-in</button>
                      )}
                      {(booking.status === 'checkedin' && checkinTokens[booking.id]) && (
                        <Link to={`/boarding-pass/${checkinTokens[booking.id]}`}>View Boarding Pass</Link>
                      )}
                      {booking.status !== 'cancelled' && (
                        <Link to={`/flight-status/${booking.flight_id}`} style={{ marginLeft: 10 }}>Track Flight</Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
};

export default Dashboard;
