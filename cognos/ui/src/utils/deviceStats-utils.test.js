import { formatYAxisNumber } from './deviceStats-utils';

describe('formatYAxisNumber', () => {
    describe('Billions formatting', () => {
        test('should format values >= 1 billion with B suffix', () => {
            expect(formatYAxisNumber(1000000000)).toBe('1.0B');
            expect(formatYAxisNumber(1500000000)).toBe('1.5B');
            expect(formatYAxisNumber(5200000000)).toBe('5.2B');
        });

        test('should format negative billions correctly', () => {
            expect(formatYAxisNumber(-1000000000)).toBe('-1.0B');
            expect(formatYAxisNumber(-2500000000)).toBe('-2.5B');
        });

        test('should round to 1 decimal place for billions', () => {
            expect(formatYAxisNumber(1234567890)).toBe('1.2B');
            expect(formatYAxisNumber(9876543210)).toBe('9.9B');
        });
    });

    describe('Millions formatting', () => {
        test('should format values >= 1 million with M suffix', () => {
            expect(formatYAxisNumber(1000000)).toBe('1.0M');
            expect(formatYAxisNumber(2500000)).toBe('2.5M');
            expect(formatYAxisNumber(50000000)).toBe('50.0M');
        });

        test('should format negative millions correctly', () => {
            expect(formatYAxisNumber(-1000000)).toBe('-1.0M');
            expect(formatYAxisNumber(-5500000)).toBe('-5.5M');
        });

        test('should round to 1 decimal place for millions', () => {
            expect(formatYAxisNumber(1234567)).toBe('1.2M');
            expect(formatYAxisNumber(9876543)).toBe('9.9M');
        });
    });

    describe('Thousands formatting', () => {
        test('should format values >= 1000 with K suffix', () => {
            expect(formatYAxisNumber(1000)).toBe('1.0K');
            expect(formatYAxisNumber(5000)).toBe('5.0K');
            expect(formatYAxisNumber(50000)).toBe('50.0K');
        });

        test('should format negative thousands correctly', () => {
            expect(formatYAxisNumber(-1000)).toBe('-1.0K');
            expect(formatYAxisNumber(-25000)).toBe('-25.0K');
        });

        test('should round to 1 decimal place for thousands', () => {
            expect(formatYAxisNumber(1234)).toBe('1.2K');
            expect(formatYAxisNumber(9876)).toBe('9.9K');
        });
    });

    describe('Small numbers (< 1000)', () => {
        test('should return numbers < 1000 as strings without formatting', () => {
            expect(formatYAxisNumber(0)).toBe('0');
            expect(formatYAxisNumber(1)).toBe('1');
            expect(formatYAxisNumber(100)).toBe('100');
            expect(formatYAxisNumber(999)).toBe('999');
        });

        test('should handle negative numbers < 1000', () => {
            expect(formatYAxisNumber(-1)).toBe('-1');
            expect(formatYAxisNumber(-100)).toBe('-100');
            expect(formatYAxisNumber(-999)).toBe('-999');
        });

        test('should handle decimal numbers < 1000', () => {
            expect(formatYAxisNumber(0.5)).toBe('0.5');
            expect(formatYAxisNumber(99.99)).toBe('99.99');
        });
    });

    describe('Edge cases', () => {
        test('should handle zero', () => {
            expect(formatYAxisNumber(0)).toBe('0');
        });

        test('should handle exactly 1000', () => {
            expect(formatYAxisNumber(1000)).toBe('1.0K');
        });

        test('should handle exactly 1 million', () => {
            expect(formatYAxisNumber(1000000)).toBe('1.0M');
        });

        test('should handle exactly 1 billion', () => {
            expect(formatYAxisNumber(1000000000)).toBe('1.0B');
        });

        test('should handle values just below thresholds', () => {
            expect(formatYAxisNumber(999)).toBe('999');
            expect(formatYAxisNumber(999999)).toBe('1000.0K');
            expect(formatYAxisNumber(999999999)).toBe('1000.0M');
        });

        test('should handle very large numbers', () => {
            expect(formatYAxisNumber(1000000000000)).toBe('1000.0B');
            expect(formatYAxisNumber(9999999999999)).toBe('10000.0B');
        });

        test('should handle floating point precision', () => {
            expect(formatYAxisNumber(1500.5)).toBe('1.5K');
            expect(formatYAxisNumber(1500000.5)).toBe('1.5M');
        });
    });

    describe('Type handling', () => {
        test('should handle numeric strings by converting them', () => {
            // Note: If your function receives strings, this test may fail
            // You might need to add Number() conversion in your function
            expect(formatYAxisNumber(Number('1000'))).toBe('1.0K');
        });

        test('should handle negative zero', () => {
            expect(formatYAxisNumber(-0)).toBe('0');
        });
    });
});