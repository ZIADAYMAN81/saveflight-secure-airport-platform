import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import QRCode from 'qrcode';
import api from '../config/api.config';
import { sanitize } from '../utils/sanitizer';

const BoardingPass = () => {
  const { token } = useParams();
  const [pass, setPass] = useState(null);
  const [qrDataUrl, setQrDataUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const response = await api.get(`/passenger/boarding-pass/${token}`);
        setPass(response.data);
        const dataUrl = await QRCode.toDataURL(response.data.secure_token, { width: 220 });
        setQrDataUrl(dataUrl);
      } catch (err) {
        setError('Unable to load boarding pass');
      }
    };
    load();
  }, [token]);

  if (error) return <div className="error" role="alert">{error}</div>;
  if (!pass) return <div>Loading boarding pass...</div>;

  return (
    <>
      <div className="page-header">
        <h1>Boarding Pass</h1>
        <p>Present the QR code at the gate. Each pass can only be used once.</p>
      </div>
      <div className="boarding-pass">
        <div className="boarding-pass-card">
          <p><strong>Passenger:</strong> {sanitize(pass.passenger_name)}</p>
          <p><strong>Flight:</strong> {pass.flight_number}</p>
          <p><strong>From:</strong> {pass.from_airport} <strong>To:</strong> {pass.to_airport}</p>
          <p><strong>Departure:</strong> {new Date(pass.departure_time).toLocaleString()}</p>
          <p><strong>Gate:</strong> {pass.gate || 'TBA'}</p>
          <p><strong>Seat:</strong> {pass.seat_number || 'Unassigned'}</p>
          <p><strong>Status:</strong> {pass.used ? 'Boarded' : 'Ready to board'}</p>
          {qrDataUrl && <img src={qrDataUrl} alt="Boarding pass QR code" width={220} height={220} />}
        </div>
      </div>
    </>
  );
};

export default BoardingPass;
