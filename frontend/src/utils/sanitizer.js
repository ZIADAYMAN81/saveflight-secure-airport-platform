import DOMPurify from 'dompurify';

// Defense-in-depth: React/JSX already escapes text content by default, so this
// is a second layer for any free-text field (incident reports, passenger
// names) that passes through more than one render path.
export const sanitize = (input) => {
  if (typeof input !== 'string') return input;
  return DOMPurify.sanitize(input, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] });
};
