import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../config/api.config';
import StatusBadge from './StatusBadge';
import { AIRPORTS } from '../utils/airports';
import { airlineCode, airlineColor, formatDuration, durationMinutes, formatTimeUTC } from '../utils/flightHelpers';

const BOOKABLE_STATUSES = new Set(['scheduled', 'boarding']);

const TIME_WINDOWS = {
  any: () => true,
  morning: (h) => h >= 5 && h < 12,
  afternoon: (h) => h >= 12 && h < 17,
  evening: (h) => h >= 17 && h < 21,
  night: (h) => h >= 21 || h < 5,
};

const FlightSearch = () => {
  const navigate = useNavigate();
  const [form, setForm] = useState({ from: '', to: '', date: '', passengers: 1 });
  const [flights, setFlights] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const [sortBy, setSortBy] = useState('departure');
  const [airlineFilter, setAirlineFilter] = useState('any');
  const [timeFilter, setTimeFilter] = useState('any');

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSearch = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const params = {};
      if (form.from) params.from_airport = form.from;
      if (form.to) params.to_airport = form.to;
      if (form.date) params.date = form.date;
      const res = await api.get('/flights', { params });
      setFlights(res.data);
    } catch (err) {
      setError('Unable to search flights. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const availableAirlines = flights ? [...new Set(flights.map((f) => airlineCode(f.flight_number)))] : [];

  const visibleFlights = (flights || [])
    .filter((f) => airlineFilter === 'any' || airlineCode(f.flight_number) === airlineFilter)
    .filter((f) => TIME_WINDOWS[timeFilter](new Date(f.departure_time).getUTCHours()))
    .sort((a, b) => {
      if (sortBy === 'price') return a.base_price - b.base_price;
      if (sortBy === 'duration') return durationMinutes(a.departure_time, a.arrival_time) - durationMinutes(b.departure_time, b.arrival_time);
      return new Date(a.departure_time) - new Date(b.departure_time);
    });

  return (
    <>
      <div className="page-header">
        <h1>Search Flights</h1>
        <p>Real-time availability - seats and pricing are always verified server-side at checkout.</p>
      </div>

      <div className="dashboard">
        <form onSubmit={handleSearch} className="flight-search-form">
          <div className="search-field">
            <label htmlFor="from">From</label>
            <select id="from" value={form.from} onChange={update('from')}>
              <option value="">Any origin</option>
              {AIRPORTS.map((a) => <option key={a.code} value={a.code}>{a.code} - {a.city}</option>)}
            </select>
          </div>
          <div className="search-field">
            <label htmlFor="to">To</label>
            <select id="to" value={form.to} onChange={update('to')}>
              <option value="">Any destination</option>
              {AIRPORTS.map((a) => <option key={a.code} value={a.code}>{a.code} - {a.city}</option>)}
            </select>
          </div>
          <div className="search-field">
            <label htmlFor="date">Departure date</label>
            <input id="date" type="date" value={form.date} onChange={update('date')} />
          </div>
          <div className="search-field search-field-narrow">
            <label htmlFor="passengers">Passengers</label>
            <input id="passengers" type="number" min={1} max={9} value={form.passengers} onChange={update('passengers')} />
          </div>
          <div className="search-field search-field-button">
            <button type="submit" disabled={loading}>{loading ? 'Searching...' : 'Search'}</button>
          </div>
        </form>

        {error && <p className="error" role="alert">{error}</p>}

        {flights && (
          <>
            <div className="results-toolbar">
              <label>
                Sort by
                <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                  <option value="departure">Departure time</option>
                  <option value="price">Price</option>
                  <option value="duration">Duration</option>
                </select>
              </label>
              <label>
                Airline
                <select value={airlineFilter} onChange={(e) => setAirlineFilter(e.target.value)}>
                  <option value="any">All airlines</option>
                  {availableAirlines.map((code) => <option key={code} value={code}>{code}</option>)}
                </select>
              </label>
              <label>
                Time
                <select value={timeFilter} onChange={(e) => setTimeFilter(e.target.value)}>
                  <option value="any">Any time</option>
                  <option value="morning">Morning (5am-12pm)</option>
                  <option value="afternoon">Afternoon (12pm-5pm)</option>
                  <option value="evening">Evening (5pm-9pm)</option>
                  <option value="night">Night (9pm-5am)</option>
                </select>
              </label>
              <label>
                Stops
                <select defaultValue="nonstop">
                  <option value="nonstop">Nonstop only</option>
                </select>
              </label>
            </div>

            {visibleFlights.length === 0 ? (
              <p>No flights match your search.</p>
            ) : (
              <div className="flight-card-list">
                {visibleFlights.map((flight) => {
                  const code = airlineCode(flight.flight_number);
                  return (
                    <div className="flight-card" key={flight.id}>
                      <div className="flight-card-airline">
                        <span className="airline-badge" style={{ background: airlineColor(code) }}>{code}</span>
                        <div>
                          <strong>{flight.flight_number}</strong>
                          <div className="flight-card-aircraft">{flight.aircraft_id || 'Aircraft TBA'}</div>
                        </div>
                      </div>

                      <div className="flight-card-route">
                        <div className="flight-card-time">
                          <strong>{formatTimeUTC(flight.departure_time)}</strong>
                          <span>{flight.from_airport}</span>
                        </div>
                        <div className="flight-card-duration">
                          {formatDuration(flight.departure_time, flight.arrival_time)}
                          <div className="flight-card-line" />
                        </div>
                        <div className="flight-card-time">
                          <strong>{formatTimeUTC(flight.arrival_time)}</strong>
                          <span>{flight.to_airport}</span>
                        </div>
                      </div>

                      <div className="flight-card-meta">
                        <StatusBadge status={flight.status} />
                        <span>{flight.available_seats} seats left</span>
                      </div>

                      <div className="flight-card-action">
                        <div className="flight-card-price">from ${flight.base_price.toFixed(0)}</div>
                        <button
                          type="button"
                          disabled={!BOOKABLE_STATUSES.has(flight.status) || flight.available_seats === 0}
                          onClick={() => navigate(`/book/${flight.id}`)}
                        >
                          {!BOOKABLE_STATUSES.has(flight.status) ? 'Not bookable'
                            : flight.available_seats === 0 ? 'Sold out' : 'Select Flight'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
};

export default FlightSearch;
