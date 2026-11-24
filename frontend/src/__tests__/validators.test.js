import { validators, validateInput } from '../utils/validators';

describe('Input Validators', () => {
  test('valid email passes', () => {
    expect(validators.email('test@example.com')).toBe(true);
  });

  test('invalid email fails', () => {
    expect(validators.email('not-an-email')).toBe(false);
  });

  test('strong password passes', () => {
    expect(validators.password('StrongPass1!')).toBe(true);
  });

  test('weak password fails', () => {
    expect(validators.password('password')).toBe(false);
  });

  test('password missing special character fails', () => {
    expect(validators.password('NoSpecialChar123')).toBe(false);
  });

  test('valid passport passes', () => {
    expect(validators.passport('AB123456')).toBe(true);
  });

  test('lowercase passport fails', () => {
    expect(validators.passport('ab123456')).toBe(false);
  });

  test('too-short passport fails', () => {
    expect(validators.passport('AB123')).toBe(false);
  });

  test('valid phone passes', () => {
    expect(validators.phone('+12125551234')).toBe(true);
  });

  test('invalid phone fails', () => {
    expect(validators.phone('not-a-phone')).toBe(false);
  });

  test('valid 6-digit TOTP code passes', () => {
    expect(validators.totpCode('123456')).toBe(true);
  });

  test('non-numeric TOTP code fails', () => {
    expect(validators.totpCode('12345a')).toBe(false);
  });

  test('validateInput throws on invalid data', () => {
    expect(() => {
      validateInput({ email: 'invalid', password: 'weak' }, { email: validators.email, password: validators.password });
    }).toThrow();
  });

  test('validateInput passes on valid data', () => {
    expect(() => {
      validateInput({ email: 'test@example.com', password: 'StrongPass1!' }, { email: validators.email, password: validators.password });
    }).not.toThrow();
  });
});
