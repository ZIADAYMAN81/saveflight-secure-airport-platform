import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { jwtDecode } from 'jwt-decode';
import api from '../config/api.config';
import { sanitize } from '../utils/sanitizer';

const StaffDashboard = () => {
  const [stats, setStats] = useState(null);
  const [role, setRole] = useState('');
  const [boardingToken, setBoardingToken] = useState('');
  const [checkinMessage, setCheckinMessage] = useState('');
  const [flightId, setFlightId] = useState('');
  const [manifest, setManifest] = useState(null);
  const [incidentType, setIncidentType] = useState('');
  const [incidentDescription, setIncidentDescription] = useState('');
  const [incidents, setIncidents] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      try {
        setRole(jwtDecode(token).role);
      } catch {
        setRole('');
      }
    }
    api.get('/staff/dashboard').then((res) => setStats(res.data)).catch(() => setError('Failed to load dashboard'));
  }, []);

  const handleCheckinPassenger = async (e) => {
    e.preventDefault();
    setCheckinMessage('');
    setError('');
    try {
      const res = await api.post('/staff/checkin-passenger', { boarding_pass_token: boardingToken });
      setCheckinMessage(res.data.message);
      setBoardingToken('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Check-in failed');
    }
  };

  const handleManifestLookup = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const res = await api.get(`/staff/flights/${flightId}/manifest`);
      setManifest(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to load manifest');
    }
  };

  const handleReportIncident = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await api.post('/staff/incidents', { incident_type: incidentType, description: incidentDescription, severity: 'medium' });
      setIncidentType('');
      setIncidentDescription('');
      const res = await api.get('/staff/incidents');
      setIncidents(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to report incident');
    }
  };

  return (
    <>
      <div className="page-header">
        <h1>Staff Dashboard</h1>
        <p>Signed in as <strong>{role}</strong>. Tools below are scoped to your role.</p>
      </div>
      <div className="dashboard">
        {error && <p className="error" role="alert">{error}</p>}

        {stats && (
          <div className="stat-grid">
            <div className="stat-card"><strong>{stats.flights_today}</strong><span>Flights today</span></div>
            <div className="stat-card"><strong>{stats.checkins_completed}</strong><span>Check-ins completed</span></div>
            <div className="stat-card"><strong>{stats.pending_boarding}</strong><span>Pending boarding</span></div>
          </div>
        )}

      {role === 'agent' && (
        <section>
          <h3>Redeem Boarding Pass</h3>
          <form onSubmit={handleCheckinPassenger}>
            <input
              placeholder="Boarding pass token"
              value={boardingToken}
              onChange={(e) => setBoardingToken(e.target.value)}
              required
            />
            <button type="submit">Check-in Passenger</button>
          </form>
          {checkinMessage && <p className="success" role="status">{checkinMessage}</p>}
        </section>
      )}

      {role === 'crew' && (
        <section>
          <h3>Flight Manifest</h3>
          <form onSubmit={handleManifestLookup}>
            <input placeholder="Flight ID" value={flightId} onChange={(e) => setFlightId(e.target.value)} required />
            <button type="submit">Load Manifest</button>
          </form>
          {manifest && (
            <ul>
              {manifest.manifest.map((p) => (
                <li key={p.booking_id}>{sanitize(p.passenger_name)} - Seat {p.seat_number || 'N/A'} - {p.status}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {role === 'security' && (
        <section>
          <h3>Report Security Incident</h3>
          <form onSubmit={handleReportIncident}>
            <input placeholder="Incident type" value={incidentType} onChange={(e) => setIncidentType(e.target.value)} required />
            <input placeholder="Description" value={incidentDescription} onChange={(e) => setIncidentDescription(e.target.value)} required />
            <button type="submit">Report</button>
          </form>
          {incidents.length > 0 && (
            <ul>
              {incidents.map((i) => (
                <li key={i.id}>[{sanitize(i.severity)}] {sanitize(i.incident_type)} - {sanitize(i.description)}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {role === 'admin' && (
        <section>
          <Link to="/admin">Go to Admin Panel</Link>
        </section>
      )}
      </div>
    </>
  );
};

export default StaffDashboard;
