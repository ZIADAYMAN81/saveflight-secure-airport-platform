import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Login from './components/Login';
import Register from './components/Register';
import TwoFactorVerify from './components/TwoFactorVerify';
import Dashboard from './components/Dashboard';
import FlightSearch from './components/FlightSearch';
import BookingForm from './components/BookingForm';
import FlightStatus from './components/FlightStatus';
import BoardingPass from './components/BoardingPass';
import StaffDashboard from './components/StaffDashboard';
import AdminPanel from './components/AdminPanel';
import AdminDashboard from './components/AdminDashboard';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';

const STAFF_ROLES = ['agent', 'crew', 'security', 'admin'];

const withLayout = (element) => <Layout>{element}</Layout>;

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/2fa-verify" element={<TwoFactorVerify />} />

      <Route path="/dashboard" element={
        <ProtectedRoute allowedRoles={['passenger']}>{withLayout(<Dashboard />)}</ProtectedRoute>
      } />
      <Route path="/flights" element={
        <ProtectedRoute allowedRoles={['passenger']}>{withLayout(<FlightSearch />)}</ProtectedRoute>
      } />
      <Route path="/book/:flightId" element={
        <ProtectedRoute allowedRoles={['passenger']}>{withLayout(<BookingForm />)}</ProtectedRoute>
      } />
      <Route path="/flight-status/:flightId" element={
        <ProtectedRoute allowedRoles={['passenger']}>{withLayout(<FlightStatus />)}</ProtectedRoute>
      } />
      <Route path="/boarding-pass/:token" element={
        <ProtectedRoute allowedRoles={['passenger']}>{withLayout(<BoardingPass />)}</ProtectedRoute>
      } />

      <Route path="/staff/dashboard" element={
        <ProtectedRoute allowedRoles={STAFF_ROLES}>{withLayout(<StaffDashboard />)}</ProtectedRoute>
      } />
      <Route path="/admin" element={
        <ProtectedRoute allowedRoles={['admin']}>{withLayout(<AdminPanel />)}</ProtectedRoute>
      } />
      <Route path="/admin/analytics" element={
        <ProtectedRoute allowedRoles={['admin']}>{withLayout(<AdminDashboard />)}</ProtectedRoute>
      } />

      <Route path="/unauthorized" element={
        <div className="unauthorized-page">
          <div>
            <h2>Access denied</h2>
            <p>You do not have permission to view this page.</p>
          </div>
        </div>
      } />
      <Route path="/" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default App;
