import '@testing-library/jest-dom';

// Ensure proper DOM environment
global.console = {
    ...console,
    // Uncomment to ignore specific console outputs in tests
    // error: jest.fn(),
    // warn: jest.fn(),
    // log: jest.fn(),
};