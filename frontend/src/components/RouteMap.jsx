import React from 'react';
import Logo from './Logo';

/**
 * Schematic (not-to-scale) route line - there's no real map/geo library wired
 * in, so this shows relative progress along the route rather than an actual
 * projected map. Position/altitude/speed shown elsewhere are simulated too
 * (see flight_status_routes.py) - this component just visualizes that number.
 */
const RouteMap = ({ from, to, fraction = 0, inFlight }) => (
  <div className="route-map">
    <div className="route-map-line">
      <span className="route-endpoint">{from}</span>
      <div className="route-track">
        <div className="route-track-fill" style={{ width: `${Math.round(fraction * 100)}%` }} />
        {inFlight && (
          <div className="route-plane" style={{ left: `${Math.round(fraction * 100)}%` }}>
            <Logo size={16} />
          </div>
        )}
      </div>
      <span className="route-endpoint">{to}</span>
    </div>
    {!inFlight && <p className="route-map-note">Not currently in flight - live position only available for departed flights.</p>}
  </div>
);

export default RouteMap;
