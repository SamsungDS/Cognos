import React from 'react';
import { getUserRole, isTokenValid } from '../components/ProtectedRoute';

// Mock atob (base64 decoder) for JWT payload decoding - consistent with your existing test
global.atob = (str) => Buffer.from(str, 'base64').toString('binary');

// Helper function to create mock tokens with expiration - similar to your existing createMockToken
const createMockTokenWithExp = (exp) => {
    const payload = {
        role: 'admin',
        exp: exp
    };
    const base64Payload = Buffer.from(JSON.stringify(payload)).toString('base64url');
    return `header.${base64Payload}.signature`;
};

// Helper to create token with custom payload
const createMockToken = (payload = { role: 'admin', exp: Math.floor(Date.now() / 1000) + 3600 }) => {
    const base64Payload = Buffer.from(JSON.stringify(payload)).toString('base64url');
    return `header.${base64Payload}.signature`;
};

// Mock Date.now for consistent testing
const mockDateNow = jest.spyOn(Date, 'now');
// Mock localStorage
const mockLocalStorage = (() => {
    let store = {};
    return {
        setItem: jest.fn((key, value) => {
            store[key] = value;
        }),
        getItem: jest.fn((key) => store[key] || null),
        removeItem: jest.fn((key) => {
            delete store[key];
        }),
        clear: jest.fn(() => {
            store = {};
        }),
    };
})();

Object.defineProperty(window, 'localStorage', {
    value: mockLocalStorage,
});

// Mock console.error to suppress error logs during testing
const mockConsoleError = jest.spyOn(console, 'error').mockImplementation(() => { });

describe('getUserRole', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        mockConsoleError.mockClear();
        mockLocalStorage.clear();
    });

    afterAll(() => {
        mockConsoleError.mockRestore();
    });

    describe('Valid JWT tokens', () => {
        test('should decode a valid JWT token and return payload', () => {
            const mockPayload = {
                sub: '1234567890',
                name: 'John Doe',
                role: 'admin',
                iat: 1516239022
            };
            const token = createMockToken(mockPayload);

            const result = getUserRole(token);

            expect(result).toEqual(mockPayload);
            expect(mockLocalStorage.setItem).toHaveBeenCalledWith('token', token);
        });

        test('should handle admin role token', () => {
            const token = createMockToken({ role: 'admin' });

            const result = getUserRole(token);

            expect(result.role).toBe('admin');
            expect(mockLocalStorage.setItem).toHaveBeenCalledWith('token', token);
        });

        test('should handle guest role token', () => {
            const token = createMockToken({ role: 'guest' });

            const result = getUserRole(token);

            expect(result.role).toBe('guest');
        });

        test('should handle user role token', () => {
            const token = createMockToken({ role: 'user' });

            const result = getUserRole(token);

            expect(result.role).toBe('user');
        });

        test('should handle token with multiple properties', () => {
            const mockPayload = {
                role: 'admin',
                userId: '123',
                email: 'test@example.com',
                permissions: ['read', 'write']
            };
            const token = createMockToken(mockPayload);

            const result = getUserRole(token);

            expect(result).toEqual(mockPayload);
        });

        test('should handle URL-safe base64 characters in token', () => {
            // Create token with characters that need URL-safe encoding
            const payload = { role: 'admin', special: 'test-with_special-chars' };
            const base64Payload = Buffer.from(JSON.stringify(payload))
                .toString('base64')
                .replace(/\+/g, '-')
                .replace(/\//g, '_')
                .replace(/=/g, '');
            const token = `header.${base64Payload}.signature`;

            const result = getUserRole(token);

            expect(result.role).toBe('admin');
        });

        test('should handle token that needs base64 padding', () => {
            const payload = { role: 'user' };
            // Create base64 without padding
            const base64Payload = Buffer.from(JSON.stringify(payload))
                .toString('base64')
                .replace(/=/g, ''); // Remove padding
            const token = `header.${base64Payload}.signature`;

            const result = getUserRole(token);

            expect(result.role).toBe('user');
        });
    });

    describe('Invalid JWT tokens', () => {
        test('should return null for malformed token (missing parts)', () => {
            const malformedToken = 'invalid.token';

            const result = getUserRole(malformedToken);

            expect(result).toBeNull();
            expect(mockConsoleError).toHaveBeenCalledWith('Error decoding token:', expect.any(Error));
        });

        test('should return null for token with only one part', () => {
            const incompleteToken = 'onlyheader';

            const result = getUserRole(incompleteToken);

            expect(result).toBeNull();
            expect(mockConsoleError).toHaveBeenCalled();
        });

        test('should return null for token with invalid base64 payload', () => {
            const invalidBase64Token = 'header.invalid@base64!.signature';

            const result = getUserRole(invalidBase64Token);

            expect(result).toBeNull();
            expect(mockConsoleError).toHaveBeenCalledWith('Error decoding token:', expect.any(Error));
        });

        test('should return null for token with invalid JSON payload', () => {
            const invalidJson = 'invalid json {';
            const invalidBase64 = Buffer.from(invalidJson).toString('base64');
            const invalidJsonToken = `header.${invalidBase64}.signature`;

            const result = getUserRole(invalidJsonToken);

            expect(result).toBeNull();
            expect(mockConsoleError).toHaveBeenCalled();
        });

        test('should return null for empty token', () => {
            const result = getUserRole('');

            expect(result).toBeNull();
            expect(mockConsoleError).toHaveBeenCalled();
        });

        test('should return null for null token', () => {
            const result = getUserRole(null);

            expect(result).toBeNull();
            expect(mockConsoleError).toHaveBeenCalled();
        });

        test('should return null for undefined token', () => {
            const result = getUserRole(undefined);

            expect(result).toBeNull();
            expect(mockConsoleError).toHaveBeenCalled();
        });
    });

    describe('localStorage interaction', () => {
        test('should store token in localStorage before processing', () => {
            const token = createMockToken({ role: 'admin' });

            getUserRole(token);

            expect(mockLocalStorage.setItem).toHaveBeenCalledWith('token', token);
            expect(mockLocalStorage.setItem).toHaveBeenCalledTimes(1);
        });

        test('should still attempt localStorage even with invalid token', () => {
            const invalidToken = 'invalid.token';

            getUserRole(invalidToken);

            expect(mockLocalStorage.setItem).toHaveBeenCalledWith('token', invalidToken);
        });

        test('should handle localStorage errors gracefully', () => {
            // Mock localStorage.setItem to throw an error
            mockLocalStorage.setItem.mockImplementationOnce(() => {
                throw new Error('localStorage is not available');
            });

            const token = createMockToken({ role: 'admin' });

            const result = getUserRole(token);

            expect(result).toBeNull();
            expect(mockConsoleError).toHaveBeenCalledWith('Error decoding token:', expect.any(Error));
        });
    });

    describe('Edge cases', () => {
        test('should handle token with empty payload object', () => {
            const token = createMockToken({});

            const result = getUserRole(token);

            expect(result).toEqual({});
        });

        test('should handle token with null values in payload', () => {
            const payload = {
                role: null,
                user: null,
                permissions: null
            };
            const token = createMockToken(payload);

            const result = getUserRole(token);

            expect(result).toEqual(payload);
        });

        test('should handle token with nested objects in payload', () => {
            const payload = {
                role: 'admin',
                user: {
                    id: 123,
                    name: 'John Doe',
                    preferences: {
                        theme: 'dark'
                    }
                }
            };
            const token = createMockToken(payload);

            const result = getUserRole(token);

            expect(result).toEqual(payload);
        });

        test('should handle token with array values in payload', () => {
            const payload = {
                role: 'admin',
                permissions: ['read', 'write', 'delete'],
                groups: [1, 2, 3]
            };
            const token = createMockToken(payload);

            const result = getUserRole(token);

            expect(result).toEqual(payload);
        });

        test('should handle token with special characters in payload', () => {
            const payload = {
                role: 'admin',
                name: 'José María',
                emoji: '🚀',
                special: '特殊文字'
            };
            const token = createMockToken(payload);

            const result = getUserRole(token);

            expect(result).toEqual(payload);
        });
    });

    describe('Integration with ProtectedRoute scenarios', () => {
        test('should decode admin token correctly for ProtectedRoute', () => {
            const token = createMockToken({ role: 'admin' });

            const result = getUserRole(token);

            expect(result.role).toBe('admin');
            // This would allow access to routes with allowedRoles: ['admin']
        });

        test('should decode guest token correctly for ProtectedRoute', () => {
            const token = createMockToken({ role: 'guest' });

            const result = getUserRole(token);

            expect(result.role).toBe('guest');
            // This would be blocked from routes with allowedRoles: ['admin']
        });

        test('should return null for invalid token in ProtectedRoute scenario', () => {
            const invalidToken = 'malformed.token';

            const result = getUserRole(invalidToken);

            expect(result).toBeNull();
            // This would cause ProtectedRoute to redirect
        });
    });
});
describe('isTokenValid', () => {
    const currentTimestamp = 1640995200; // January 1, 2022 00:00:00 UTC
    const currentTimeMs = currentTimestamp * 1000;

    beforeEach(() => {
        jest.clearAllMocks();
        mockConsoleError.mockClear();
        mockDateNow.mockReturnValue(currentTimeMs);
    });

    afterAll(() => {
        mockConsoleError.mockRestore();
        mockDateNow.mockRestore();
    });

    describe('Valid tokens', () => {
        test('should return true for non-expired token', () => {
            const futureExp = currentTimestamp + 3600; // 1 hour in future
            const token = createMockTokenWithExp(futureExp);

            const result = isTokenValid(token);

            expect(result).toBe(true);
        });

        test('should return true for token expiring in 1 second', () => {
            const futureExp = currentTimestamp + 1; // 1 second in future
            const token = createMockTokenWithExp(futureExp);

            const result = isTokenValid(token);

            expect(result).toBe(true);
        });

        test('should handle token with URL-safe base64 characters', () => {
            const payload = { role: 'admin', exp: currentTimestamp + 3600 };
            // Create base64 with URL-safe characters
            const base64Payload = Buffer.from(JSON.stringify(payload))
                .toString('base64')
                .replace(/\+/g, '-')
                .replace(/\//g, '_')
                .replace(/=/g, '');
            const token = `header.${base64Payload}.signature`;

            const result = isTokenValid(token);

            expect(result).toBe(true);
        });

        test('should handle token that needs base64 padding', () => {
            const payload = { exp: currentTimestamp + 3600 };
            // Create base64 without padding
            const base64Payload = Buffer.from(JSON.stringify(payload))
                .toString('base64')
                .replace(/=/g, ''); // Remove padding
            const token = `header.${base64Payload}.signature`;

            const result = isTokenValid(token);

            expect(result).toBe(true);
        });

        test('should handle token with additional payload properties', () => {
            const payload = {
                role: 'admin',
                userId: '123',
                email: 'test@example.com',
                exp: currentTimestamp + 3600
            };
            const token = createMockToken(payload);

            const result = isTokenValid(token);

            expect(result).toBe(true);
        });
    });

    describe('Expired tokens', () => {
        test('should return false for expired token', () => {
            const pastExp = currentTimestamp - 3600; // 1 hour in past
            const token = createMockTokenWithExp(pastExp);

            const result = isTokenValid(token);

            expect(result).toBe(false);
        });

        test('should return false for token that just expired', () => {
            const pastExp = currentTimestamp - 1; // 1 second in past
            const token = createMockTokenWithExp(pastExp);

            const result = isTokenValid(token);

            expect(result).toBe(false);
        });

        test('should return false for token with exp equal to current time', () => {
            const currentExp = currentTimestamp; // Exactly current time
            const token = createMockTokenWithExp(currentExp);

            const result = isTokenValid(token);

            expect(result).toBe(false);
        });

        test('should return false for token with very old expiration', () => {
            const veryOldExp = currentTimestamp - 86400; // 24 hours ago
            const token = createMockTokenWithExp(veryOldExp);

            const result = isTokenValid(token);

            expect(result).toBe(false);
        });
    });

    describe('Invalid tokens', () => {
        test('should return false for token without exp field', () => {
            const payloadWithoutExp = { role: 'admin', userId: '123' };
            const token = createMockToken(payloadWithoutExp);

            const result = isTokenValid(token);

            expect(result).toBe(false);
        });

        test('should return false for token with null exp field', () => {
            const payloadWithNullExp = { role: 'admin', exp: null };
            const token = createMockToken(payloadWithNullExp);

            const result = isTokenValid(token);

            expect(result).toBe(false);
        });

        test('should return false for token with invalid exp field type', () => {
            const payloadWithStringExp = { role: 'admin', exp: 'not-a-number' };
            const token = createMockToken(payloadWithStringExp);

            const result = isTokenValid(token);

            expect(result).toBe(false);
        });
    });

    describe('Edge cases', () => {
        test('should handle token with exp as string number', () => {
            const futureExp = (currentTimestamp + 3600).toString();
            const payload = { role: 'admin', exp: futureExp };
            const token = createMockToken(payload);

            const result = isTokenValid(token);

            expect(result).toBe(true);
        });

        test('should handle token with exp as float', () => {
            const futureExp = currentTimestamp + 3600.5;
            const payload = { role: 'admin', exp: futureExp };
            const token = createMockToken(payload);

            const result = isTokenValid(token);

            expect(result).toBe(true);
        });

        test('should handle token with very large exp value', () => {
            const veryFutureExp = currentTimestamp + 999999999;
            const payload = { role: 'admin', exp: veryFutureExp };
            const token = createMockToken(payload);

            const result = isTokenValid(token);

            expect(result).toBe(true);
        });

        test('should handle token with negative exp value', () => {
            const negativeExp = -1000;
            const payload = { role: 'admin', exp: negativeExp };
            const token = createMockToken(payload);

            const result = isTokenValid(token);

            expect(result).toBe(false);
        });

        test('should handle token with zero exp value', () => {
            const zeroExp = 0;
            const payload = { role: 'admin', exp: zeroExp };
            const token = createMockToken(payload);

            const result = isTokenValid(token);

            expect(result).toBe(false);
        });

        test('should handle token with special characters in other fields', () => {
            const payload = {
                role: 'admin',
                name: 'José María',
                emoji: '🚀',
                special: '特殊文字',
                exp: currentTimestamp + 3600
            };
            const token = createMockToken(payload);

            const result = isTokenValid(token);

            expect(result).toBe(true);
        });
    });

    describe('Time-based scenarios', () => {
        test('should handle different current times correctly', () => {
            const tokenExp = 1640995200 + 3600; // Token expires 1 hour after base time
            const token = createMockTokenWithExp(tokenExp);

            // Test when current time is before expiration
            mockDateNow.mockReturnValue((tokenExp - 1800) * 1000); // 30 minutes before exp
            expect(isTokenValid(token)).toBe(true);

            // Test when current time is after expiration  
            mockDateNow.mockReturnValue((tokenExp + 1800) * 1000); // 30 minutes after exp
            expect(isTokenValid(token)).toBe(false);
        });

        test('should handle millisecond precision correctly', () => {
            const tokenExp = currentTimestamp + 1; // 1 second in future
            const token = createMockTokenWithExp(tokenExp);

            // Current time is 500ms before expiration
            mockDateNow.mockReturnValue(currentTimeMs + 500);
            expect(isTokenValid(token)).toBe(true);

            // Current time is 500ms after expiration
            mockDateNow.mockReturnValue(currentTimeMs + 1500);
            expect(isTokenValid(token)).toBe(false);
        });
    });

    describe('Integration with ProtectedRoute scenarios', () => {
        test('should validate admin token correctly for ProtectedRoute', () => {
            const futureExp = currentTimestamp + 3600;
            const token = createMockTokenWithExp(futureExp);

            const result = isTokenValid(token);

            expect(result).toBe(true);
            // This would allow ProtectedRoute to proceed with role checking
        });

        test('should reject expired token for ProtectedRoute', () => {
            const pastExp = currentTimestamp - 3600;
            const token = createMockTokenWithExp(pastExp);

            const result = isTokenValid(token);

            expect(result).toBe(false);
            // This would cause ProtectedRoute to redirect regardless of role
        });

        test('should reject malformed token for ProtectedRoute', () => {
            const malformedToken = 'invalid.token';

            const result = isTokenValid(malformedToken);

            expect(result).toBe(false);
            // This would cause ProtectedRoute to redirect
        });
    });
});