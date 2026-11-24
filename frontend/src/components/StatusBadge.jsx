import React from 'react';

const StatusBadge = ({ status }) => (
  <span className={`badge badge-${status}`}>{status}</span>
);

export default StatusBadge;
