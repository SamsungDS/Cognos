// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// Ensure proper DOM environment
global.console = {
    ...console,
    // Uncomment to ignore specific console outputs in tests
    // error: jest.fn(),
    // warn: jest.fn(),
    // log: jest.fn(),
};

