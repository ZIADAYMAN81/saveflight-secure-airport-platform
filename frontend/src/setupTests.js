import '@testing-library/jest-dom';

// jsdom doesn't implement ResizeObserver (recharts' ResponsiveContainer needs
// it); it's present in every real browser this app targets.
global.ResizeObserver = global.ResizeObserver || class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
