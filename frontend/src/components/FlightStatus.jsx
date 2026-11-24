import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../config/api.config';
import StatusBadge from './StatusBadge';
import FlightTimeline from './FlightTimeline';
import RouteMap from './RouteMap';

const BOARDING_GROUP = { first: 'Group 1', business: 'Group 2', economy: 'Group 3' };

const FlightStatus = () => {
  const { flightId } = useParams();
  const [flight, setFlight] = useState(null);
  const [statusData, setStatusData] = useState(null);
  const [myBooking, setMyBooking] = useState(null);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [flightRes, statusRes, bookingsRes] = await Promise.all([
        api.get(`/flights/${flightId}`),
        api.get(`/flights/${flightId}/status`),
        api.get('/passenger/bookings').catch(() => ({ data: [] })),
      ]);
      setFlight(flightRes.data);
      setStatusData(statusRes.data);
      setMyBooking(bookingsRes.data.find((b) => b.flight_id === Number(flightId) && b.status !== 'cancelled') || null);
    } catch (err) {
      setError('Unable to load flight status');
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000); // simple "live" refresh
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flightId]);

  if (error) return <div className="error" role="alert">{error}</div>;
  if (!flight || !statusData) return <div>Loading flight status...</div>;

  return (
    <>
      <div className="page-header">
        <h1>Flight Status</h1>
        <p>Auto-refreshes every 30 seconds.</p>
      </div>

      <div className="dashboard flight-status-card">
        <div className="flight-status-header">
          <div>
            <h2>{flight.flight_number}</h2>
            <p>{flight.from_airport} &rarr; {flight.to_airport} &middot; {flight.aircraft_id || 'Aircraft TBA'}</p>
          </div>
          <StatusBadge status={flight.status} />
        </div>

        <div className="flight-status-gate-row">
          <div className="stat-card"><strong>{flight.gate || 'TBA'}</strong><span>Gate</span></div>
          <div className="stat-card"><strong>{flight.terminal || 'TBA'}</strong><span>Terminal</span></div>
          {statusData.live && (
            <>
              <div className="stat-card"><strong>{statusData.live.altitude_ft.toLocaleString()} ft</strong><span>Altitude (simulated)</span></div>
              <div className="stat-card"><strong>{statusData.live.speed_kts} kts</strong><span>Speed (simulated)</span></div>
            </>
          )}
        </div>

        {statusData.alerts.length > 0 && (
          <section>
            <h3>Notifications</h3>
            {statusData.alerts.map((a, i) => (
              <p key={i} className={a.type === 'final_call' ? 'error' : 'error'}>{a.message}</p>
            ))}
          </section>
        )}

        <section>
          <h3>Route</h3>
          <RouteMap
            from={flight.from_airport}
            to={flight.to_airport}
            fraction={statusData.live?.progress_fraction || 0}
            inFlight={flight.status === 'departed'}
          />
          {statusData.live?.distance_remaining_km != null && (
            <p>{statusData.live.distance_remaining_km.toLocaleString()} km remaining - about {statusData.live.time_to_destination_minutes} minutes to destination.</p>
          )}
        </section>

        <section>
          <h3>Timeline</h3>
          <FlightTimeline timeline={statusData.timeline} />
        </section>

        {myBooking && (
          <section>
            <h3>Your booking</h3>
            <div className="stat-grid">
              <div className="stat-card"><strong>{myBooking.seat_number || 'Unassigned'}</strong><span>Seat</span></div>
              <div className="stat-card"><strong>{BOARDING_GROUP[myBooking.seat_class] || 'N/A'}</strong><span>Boarding group</span></div>
              <div className="stat-card"><strong>{myBooking.status === 'checkedin' ? 'Checked in' : 'Not checked in'}</strong><span>Status</span></div>
            </div>
          </section>
        )}
      </div>
    </>
  );
};

export default FlightStatus;
