import React, { useEffect, useState } from 'react';
import api from '../config/api.config';

const AdminPanel = () => {
  const [users, setUsers] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [chainIntact, setChainIntact] = useState(null);
  const [error, setError] = useState('');
  const [staffForm, setStaffForm] = useState({ email: '', password: '', full_name: '', role: 'agent', department: '', employee_id: '' });
  const [message, setMessage] = useState('');

  const load = async () => {
    try {
      const [usersRes, logsRes, verifyRes] = await Promise.all([
        api.get('/admin/users'),
        api.get('/admin/audit-logs?limit=50'),
        api.get('/admin/audit-logs/verify'),
      ]);
      setUsers(usersRes.data);
      setAuditLogs(logsRes.data);
      setChainIntact(verifyRes.data.intact);
    } catch (err) {
      setError('Failed to load admin data');
    }
  };

  useEffect(() => {
    load();
  }, []);

  const update = (field) => (e) => setStaffForm((f) => ({ ...f, [field]: e.target.value }));

  const handleCreateStaff = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    try {
      await api.post('/admin/create-staff', staffForm);
      setMessage(`Staff account created for ${staffForm.email}`);
      setStaffForm({ email: '', password: '', full_name: '', role: 'agent', department: '', employee_id: '' });
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create staff account');
    }
  };

  return (
    <>
      <div className="page-header">
        <h1>Admin Panel</h1>
        <p>Manage staff accounts and review the tamper-evident security audit log.</p>
      </div>
      <div className="dashboard">
        {error && <p className="error" role="alert">{error}</p>}
        {message && <p className="success" role="status">{message}</p>}

        <div className="stat-grid">
          <div className="stat-card">
            <strong>{users.length}</strong>
            <span>Total users</span>
          </div>
          <div className="stat-card">
            <strong style={{ color: chainIntact ? 'var(--success)' : chainIntact === false ? 'var(--danger)' : undefined }}>
              {chainIntact === null ? '...' : chainIntact ? 'Intact' : 'Tampered'}
            </strong>
            <span>Audit log integrity</span>
          </div>
          <div className="stat-card">
            <strong>{auditLogs.length}</strong>
            <span>Recent log entries</span>
          </div>
        </div>

        <section>
          <h3>Create staff account</h3>
          <form onSubmit={handleCreateStaff}>
            <input placeholder="Full name" value={staffForm.full_name} onChange={update('full_name')} required />
            <input placeholder="Email" type="email" value={staffForm.email} onChange={update('email')} required />
            <input placeholder="Password" type="password" value={staffForm.password} onChange={update('password')} required />
            <select value={staffForm.role} onChange={update('role')}>
              <option value="agent">Check-in Agent</option>
              <option value="crew">Flight Crew</option>
              <option value="security">Security Staff</option>
              <option value="admin">Admin</option>
            </select>
            <input placeholder="Department" value={staffForm.department} onChange={update('department')} />
            <input placeholder="Employee ID" value={staffForm.employee_id} onChange={update('employee_id')} required />
            <button type="submit">Create</button>
          </form>
        </section>

        <section>
          <h3>Users ({users.length})</h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Email</th><th>Role</th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}><td>{u.email}</td><td>{u.role}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h3>Recent audit log</h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Status</th><th>Action</th><th>Resource</th><th>Timestamp</th></tr>
              </thead>
              <tbody>
                {auditLogs.map((log) => (
                  <tr key={log.id}>
                    <td>{log.status}</td>
                    <td>{log.action}</td>
                    <td>{log.resource}</td>
                    <td>{new Date(log.timestamp).toLocaleString()}</td>
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

export default AdminPanel;
