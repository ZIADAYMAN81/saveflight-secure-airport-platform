import React from 'react';

const STAGE_LABELS = {
  scheduled: 'Scheduled',
  boarding: 'Boarding',
  pushback: 'Pushback',
  departed: 'Departed',
  arrived: 'Arrived',
};

const FlightTimeline = ({ timeline }) => (
  <ol className="flight-timeline">
    {timeline.map((stage, idx) => {
      const isNext = !stage.completed && (idx === 0 || timeline[idx - 1].completed);
      return (
        <li key={stage.name} className={stage.completed ? 'done' : isNext ? 'current' : 'upcoming'}>
          <span className="timeline-dot">{stage.completed ? '✓' : isNext ? '⏳' : ''}</span>
          <div>
            <strong>{STAGE_LABELS[stage.name] || stage.name}</strong>
            <div className="timeline-time">{new Date(stage.at).toLocaleString('en-US', { timeZone: 'UTC' })} UTC</div>
          </div>
        </li>
      );
    })}
  </ol>
);

export default FlightTimeline;
