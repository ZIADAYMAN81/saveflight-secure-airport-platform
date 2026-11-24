export const validators = {
  email: (email) => {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
  },
  password: (password) => {
    const regex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$/;
    return regex.test(password);
  },
  passport: (passport) => {
    const regex = /^[A-Z0-9]{6,9}$/;
    return regex.test(passport);
  },
  phone: (phone) => {
    const regex = /^\+?[1-9]\d{1,14}$/;
    return regex.test(phone);
  },
  fullName: (name) => {
    return typeof name === 'string' && name.trim().length >= 2 && name.trim().length <= 100;
  },
  totpCode: (code) => {
    return /^\d{6}$/.test(code);
  },
};

export class ValidationError extends Error {
  constructor(errors) {
    super('Validation failed');
    this.name = 'ValidationError';
    this.errors = errors;
  }
}

export const validateInput = (data, rules) => {
  const errors = {};
  Object.entries(rules).forEach(([field, validator]) => {
    if (!validator(data[field] || '')) {
      errors[field] = 'Invalid value';
    }
  });
  if (Object.keys(errors).length) {
    throw new ValidationError(errors);
  }
  return true;
};
