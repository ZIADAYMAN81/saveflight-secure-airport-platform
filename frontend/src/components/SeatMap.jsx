import React, { useEffect, useState } from 'react';
import api from '../config/api.config';

const CLASS_LABELS = { first: 'First Class', business: 'Business', economy: 'Economy' };
const LEGROOM = {
  first: '78" pitch, lie-flat seat',
  business: '40" pitch, deep recline',
  economy: '31" pitch, standard recline',
};

const SeatButton = ({ seat, selected, onClick }) => {
  const state = selected ? 'selected' : seat.status;
  const title = seat.status === 'occupied' ? 'Already booked by another passenger'
    : seat.status === 'restricted' ? 'Restricted - not available for booking (crew/structural)'
    : `${seat.seat_number} - ${CLASS_LABELS[seat.seat_class]} - $${seat.price.toFixed(2)}`;

  return (
    <button
      type="button"
      className={`seat seat-${state}${seat.is_exit_row ? ' seat-exit-row' : ''}`}
      title={title}
      disabled={seat.status !== 'available' && !selected}
      onClick={() => onClick(seat)}
    >
      {seat.seat_number.replace(/^\d+/, '')}
    </button>
  );
};

/**
 * Selecting a seat here does NOT lock it server-side - it's only reserved for
 * real once a booking is actually created for it (booking_routes.py rejects
 * the create if someone else has already booked that seat_id in the meantime).
 * That is the actual "lock": the database's own collision check at write time,
 * not a client-side hold that could go stale.
 */
const SeatMap = ({ flightId, onConfirm }) => {
  const [seatData, setSeatData] = useState(null);
  const [selected, setSelected] = useState([]);
  const [popupSeat, setPopupSeat] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get(`/flights/${flightId}/seats`)
      .then((res) => setSeatData(res.data))
      .catch(() => setError('Unable to load seat map'));
  }, [flightId]);

  if (error) return <div className="error" role="alert">{error}</div>;
  if (!seatData) return <div>Loading seat map...</div>;

  const rows = {};
  seatData.seats.forEach((seat) => {
    const rowNum = parseInt(seat.seat_number, 10);
    (rows[rowNum] = rows[rowNum] || []).push(seat);
  });
  const rowNumbers = Object.keys(rows).map(Number).sort((a, b) => a - b);

  const isSelected = (seat) => selected.some((s) => s.id === seat.id);

  const handleSeatClick = (seat) => {
    if (isSelected(seat)) {
      setSelected((prev) => prev.filter((s) => s.id !== seat.id));
      return;
    }
    if (seat.status !== 'available') return;
    setPopupSeat(seat);
  };

  const confirmAddSeat = () => {
    setSelected((prev) => [...prev, popupSeat]);
    setPopupSeat(null);
  };

  const removeSeat = (seatId) => setSelected((prev) => prev.filter((s) => s.id !== seatId));
  const total = selected.reduce((sum, s) => sum + s.price, 0);

  let lastClass = null;

  return (
    <div className="seat-map">
      <div className="seat-legend">
        <span className="legend-item"><span className="seat-swatch seat-available" /> Available</span>
        <span className="legend-item"><span className="seat-swatch seat-occupied" /> Occupied</span>
        <span className="legend-item"><span className="seat-swatch seat-selected" /> Selected</span>
        <span className="legend-item"><span className="seat-swatch seat-restricted" /> Restricted</span>
      </div>

      <div className="seat-grid">
        {rowNumbers.map((rowNum) => {
          const rowSeats = [...rows[rowNum]].sort((a, b) => a.seat_number.localeCompare(b.seat_number));
          const seatClass = rowSeats[0].seat_class;
          const showDivider = seatClass !== lastClass;
          lastClass = seatClass;
          return (
            <React.Fragment key={rowNum}>
              {showDivider && (
                <div className="class-divider">
                  {CLASS_LABELS[seatClass]}
                  <span className="class-divider-price">${rowSeats[0].price.toFixed(0)}+</span>
                </div>
              )}
              <div className="seat-row">
                <span className="row-number">{rowNum}</span>
                {rowSeats.slice(0, 3).map((seat) => (
                  <SeatButton key={seat.id} seat={seat} selected={isSelected(seat)} onClick={handleSeatClick} />
                ))}
                <span className="aisle-gap" />
                {rowSeats.slice(3, 6).map((seat) => (
                  <SeatButton key={seat.id} seat={seat} selected={isSelected(seat)} onClick={handleSeatClick} />
                ))}
              </div>
            </React.Fragment>
          );
        })}
      </div>

      {popupSeat && (
        <div className="seat-popup-backdrop" onClick={() => setPopupSeat(null)}>
          <div className="seat-popup" onClick={(e) => e.stopPropagation()}>
            <h4>Seat {popupSeat.seat_number}</h4>
            <p>{CLASS_LABELS[popupSeat.seat_class]} - {popupSeat.position}</p>
            <p>{LEGROOM[popupSeat.seat_class]}</p>
            {popupSeat.is_exit_row && (
              <p className="exit-row-warning">Exit row - you must be able and willing to assist in an emergency.</p>
            )}
            <p className="seat-popup-price">${popupSeat.price.toFixed(2)}</p>
            <button onClick={confirmAddSeat}>Add seat</button>
            <button type="button" className="secondary-btn" onClick={() => setPopupSeat(null)}>Cancel</button>
          </div>
        </div>
      )}

      {selected.length > 0 && (
        <div className="seat-cart">
          <h4>Selected seats ({selected.length})</h4>
          <ul>
            {selected.map((s) => (
              <li key={s.id}>
                {s.seat_number} ({CLASS_LABELS[s.seat_class]}) - ${s.price.toFixed(2)}
                <button type="button" className="link-btn" onClick={() => removeSeat(s.id)}>Remove</button>
              </li>
            ))}
          </ul>
          <p className="seat-cart-total">Total: ${total.toFixed(2)}</p>
          <button type="button" onClick={() => onConfirm(selected)}>Continue to booking</button>
        </div>
      )}
    </div>
  );
};

export default SeatMap;
