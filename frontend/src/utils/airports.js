// Major airports this demo's flight network actually uses (matches the
// seeded routes and flight_status_routes.py's coordinate table).
export const AIRPORTS = [
  { code: 'CAI', city: 'Cairo', name: 'Cairo International' },
  { code: 'JFK', city: 'New York', name: 'John F. Kennedy Intl' },
  { code: 'DXB', city: 'Dubai', name: 'Dubai International' },
  { code: 'LHR', city: 'London', name: 'Heathrow' },
  { code: 'FRA', city: 'Frankfurt', name: 'Frankfurt Airport' },
  { code: 'JED', city: 'Jeddah', name: 'King Abdulaziz Intl' },
  { code: 'DOH', city: 'Doha', name: 'Hamad International' },
  { code: 'IST', city: 'Istanbul', name: 'Istanbul Airport' },
  { code: 'CDG', city: 'Paris', name: 'Charles de Gaulle' },
  { code: 'AUH', city: 'Abu Dhabi', name: 'Zayed International' },
  { code: 'RUH', city: 'Riyadh', name: 'King Khalid Intl' },
  { code: 'YVR', city: 'Vancouver', name: 'Vancouver Intl' },
  { code: 'LAX', city: 'Los Angeles', name: 'Los Angeles Intl' },
];

export const airportLabel = (code) => {
  const a = AIRPORTS.find((x) => x.code === code);
  return a ? `${a.code} - ${a.city}` : code;
};
