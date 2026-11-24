import React, { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import api from '../config/api.config';

const PIE_COLORS = ['#2563eb', '#0d9488', '#e8a52e', '#7c3aed', '#be123c'];

const AdminDashboard = () => {
  const [overview, setOverview] = useState(null);
  const [hourly, setHourly] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [revenue, setRevenue] = useState([]);
  const [terminals, setTerminals] = useState([]);
  const [realtime, setRealtime] = useState(null);
  const [activity, setActivity] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [ov, hr, rt, rev, term, live, act, al] = await Promise.all([
        api.get('/admin/analytics/overview'),
        api.get('/admin/analytics/hourly-checkins'),
        api.get('/admin/analytics/popular-routes'),
        api.get('/admin/analytics/revenue-by-airline'),
        api.get('/admin/analytics/passengers-by-terminal'),
        api.get('/admin/analytics/realtime'),
        api.get('/admin/analytics/activity-feed?limit=15'),
        api.get('/admin/analytics/alerts'),
      ]);
      setOverview(ov.data);
      setHourly(hr.data.map((h) => ({ ...h, label: new Date(h.hour).toLocaleTimeString('en-US', { hour: '2-digit', timeZone: 'UTC' }) })));
      setRoutes(rt.data);
      setRevenue(rev.data);
      setTerminals(term.data);
      setRealtime(live.data);
      setActivity(act.data);
      setAlerts(al.data);
    } catch (err) {
      setError('Unable to load analytics (admin access required)');
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  if (error) return <div className="error" role="alert">{error}</div>;
  if (!overview) return <div>Loading dashboard...</div>;

  return (
    <>
      <div className="page-header">
        <h1>Admin Analytics</h1>
        <p>Every number below is computed from real bookings/payments/check-ins - see /metrics + Grafana for uptime/latency.</p>
      </div>

      <div className="dashboard">
        <div className="stat-grid">
          <div className="stat-card"><strong>{overview.flights_today}</strong><span>Flights today</span></div>
          <div className="stat-card"><strong>{overview.checkins_today}</strong><span>Check-ins today</span></div>
          <div className="stat-card"><strong>${overview.revenue_today.toFixed(0)}</strong><span>Revenue today</span></div>
          <div className="stat-card"><strong>{overview.avg_booking_to_checkin_minutes ?? 'N/A'}</strong><span>Avg. min: booking to check-in</span></div>
          <div className="stat-card"><strong>{overview.active_staff}</strong><span>Active staff</span></div>
        </div>

        {alerts.length > 0 && (
          <section>
            <h3>Alerts</h3>
            {alerts.map((a, i) => <p key={i} className="error" role="alert">[{a.severity}] {a.message}</p>)}
          </section>
        )}

        {realtime && (
          <section>
            <h3>Real-time</h3>
            <div className="stat-grid">
              <div className="stat-card"><strong>{realtime.flights_departing_next_2h}</strong><span>Departing (2h)</span></div>
              <div className="stat-card"><strong>{realtime.gates_in_use}</strong><span>Gates in use</span></div>
              <div className="stat-card"><strong>{realtime.passengers_in_terminal}</strong><span>Passengers in terminal</span></div>
              {Object.entries(realtime.staff_by_department).map(([dept, count]) => (
                <div className="stat-card" key={dept}><strong>{count}</strong><span>{dept}</span></div>
              ))}
            </div>
          </section>
        )}

        <section>
          <h3>Check-in volume by hour (last 24h)</h3>
          {hourly.length === 0 ? <p>No check-ins in this window.</p> : (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={hourly}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" fontSize={12} />
                  <YAxis allowDecimals={false} fontSize={12} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>

        <section>
          <h3>Revenue by airline</h3>
          {revenue.length === 0 ? <p>No completed payments yet.</p> : (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={revenue}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="airline" fontSize={12} />
                  <YAxis fontSize={12} />
                  <Tooltip formatter={(v) => `$${v}`} />
                  <Bar dataKey="revenue" fill="#0d9488" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>

        <section>
          <h3>Passengers by terminal</h3>
          {terminals.every((t) => t.passengers === 0) || terminals.length === 0 ? <p>No terminal data yet.</p> : (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={terminals} dataKey="passengers" nameKey="terminal" outerRadius={80} label>
                    {terminals.map((entry, i) => <Cell key={entry.terminal} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>

        <section>
          <h3>Popular routes</h3>
          <div className="table-scroll">
            <table>
              <thead><tr><th>From</th><th>To</th><th>Bookings</th></tr></thead>
              <tbody>
                {routes.map((r) => (
                  <tr key={`${r.from_airport}-${r.to_airport}`}>
                    <td>{r.from_airport}</td><td>{r.to_airport}</td><td>{r.bookings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h3>Activity feed</h3>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Status</th><th>Action</th><th>Resource</th><th>Time</th></tr></thead>
              <tbody>
                {activity.map((a) => (
                  <tr key={a.id}>
                    <td>{a.status}</td><td>{a.action}</td><td>{a.resource}</td>
                    <td>{new Date(a.timestamp).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
};

export default AdminDashboard;
