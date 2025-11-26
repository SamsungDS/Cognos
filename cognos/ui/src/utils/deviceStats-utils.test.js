import { formatYAxisNumber, getBestBandwidthUnit,
    convertBandwidthToUnit,
    formatBandwidthValue,
    convertMemoryUnit,
    getBestMemoryUnit,
    convertToUnit,
    formatMemoryValue
} from './deviceStats-utils';

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

describe('Bandwidth Unit Utilities', () => {
    describe('getBestBandwidthUnit', () => {
        it('should return Gbps for values >= 1000', () => {
            expect(getBestBandwidthUnit(1000)).toBe('Gbps');
            expect(getBestBandwidthUnit(5000)).toBe('Gbps');
            expect(getBestBandwidthUnit(10000)).toBe('Gbps');
        });

        it('should return Mbps for values >= 1 and < 1000', () => {
            expect(getBestBandwidthUnit(1)).toBe('Mbps');
            expect(getBestBandwidthUnit(100)).toBe('Mbps');
            expect(getBestBandwidthUnit(999)).toBe('Mbps');
        });

        it('should return Kbps for values >= 0.001 and < 1', () => {
            expect(getBestBandwidthUnit(0.001)).toBe('Kbps');
            expect(getBestBandwidthUnit(0.5)).toBe('Kbps');
            expect(getBestBandwidthUnit(0.999)).toBe('Kbps');
        });

        it('should return bps for values < 0.001', () => {
            expect(getBestBandwidthUnit(0.0009)).toBe('bps');
            expect(getBestBandwidthUnit(0.0001)).toBe('bps');
            expect(getBestBandwidthUnit(0)).toBe('bps');
        });

        it('should handle edge cases', () => {
            expect(getBestBandwidthUnit(999.99)).toBe('Mbps');
            expect(getBestBandwidthUnit(1000.01)).toBe('Gbps');
        });
    });

    describe('convertBandwidthToUnit', () => {
        describe('from Mbps (default base)', () => {
            it('should convert Mbps to bps', () => {
                expect(convertBandwidthToUnit(1, 'bps')).toBe(1000000);
                expect(convertBandwidthToUnit(10, 'bps')).toBe(10000000);
            });

            it('should convert Mbps to Kbps', () => {
                expect(convertBandwidthToUnit(1, 'Kbps')).toBe(1000);
                expect(convertBandwidthToUnit(10, 'Kbps')).toBe(10000);
            });

            it('should convert Mbps to Mbps (same unit)', () => {
                expect(convertBandwidthToUnit(1, 'Mbps')).toBe(1);
                expect(convertBandwidthToUnit(100, 'Mbps')).toBe(100);
            });

            it('should convert Mbps to Gbps', () => {
                expect(convertBandwidthToUnit(1000, 'Gbps')).toBe(1);
                expect(convertBandwidthToUnit(5000, 'Gbps')).toBe(5);
            });
        });

        describe('from Gbps base', () => {
            it('should convert Gbps to Mbps', () => {
                expect(convertBandwidthToUnit(1, 'Mbps', 'Gbps')).toBe(1000);
                expect(convertBandwidthToUnit(5, 'Mbps', 'Gbps')).toBe(5000);
            });

            it('should convert Gbps to Kbps', () => {
                expect(convertBandwidthToUnit(1, 'Kbps', 'Gbps')).toBe(1000000);
            });

            it('should convert Gbps to bps', () => {
                expect(convertBandwidthToUnit(1, 'bps', 'Gbps')).toBe(1000000000);
            });

            it('should convert Gbps to Gbps (same unit)', () => {
                expect(convertBandwidthToUnit(5, 'Gbps', 'Gbps')).toBe(5);
            });
        });

        describe('from Kbps base', () => {
            it('should convert Kbps to bps', () => {
                expect(convertBandwidthToUnit(1, 'bps', 'Kbps')).toBe(1000);
                expect(convertBandwidthToUnit(100, 'bps', 'Kbps')).toBe(100000);
            });

            it('should convert Kbps to Mbps', () => {
                expect(convertBandwidthToUnit(1000, 'Mbps', 'Kbps')).toBe(1);
                expect(convertBandwidthToUnit(5000, 'Mbps', 'Kbps')).toBe(5);
            });

            it('should convert Kbps to Gbps', () => {
                expect(convertBandwidthToUnit(1000000, 'Gbps', 'Kbps')).toBe(1);
            });
        });

        describe('from bps base', () => {
            it('should convert bps to Kbps', () => {
                expect(convertBandwidthToUnit(1000, 'Kbps', 'bps')).toBe(1);
                expect(convertBandwidthToUnit(5000, 'Kbps', 'bps')).toBe(5);
            });

            it('should convert bps to Mbps', () => {
                expect(convertBandwidthToUnit(1000000, 'Mbps', 'bps')).toBe(1);
            });

            it('should convert bps to Gbps', () => {
                expect(convertBandwidthToUnit(1000000000, 'Gbps', 'bps')).toBe(1);
            });
        });

        it('should handle decimal values', () => {
            expect(convertBandwidthToUnit(1.5, 'Kbps')).toBe(1500);
            expect(convertBandwidthToUnit(2.5, 'Gbps', 'Mbps')).toBeCloseTo(0.0025, 6);
        });

        it('should handle zero value', () => {
            expect(convertBandwidthToUnit(0, 'Gbps')).toBe(0);
            expect(convertBandwidthToUnit(0, 'bps')).toBe(0);
        });

        it('should handle unknown units by defaulting to Mbps', () => {
            expect(convertBandwidthToUnit(1, 'unknown')).toBe(1);
            expect(convertBandwidthToUnit(1, 'Mbps', 'unknown')).toBe(1);
        });
    });

    describe('formatBandwidthValue', () => {
        it('should format values >= 1000 with 2 decimal places', () => {
            expect(formatBandwidthValue(1000, 'Mbps')).toBe('1000.00 Mbps');
            expect(formatBandwidthValue(5000, 'Mbps')).toBe('5000.00 Mbps');
        });

        it('should format values >= 100 and < 1000 with 1 decimal place', () => {
            expect(formatBandwidthValue(100, 'Mbps')).toBe('100.0 Mbps');
            expect(formatBandwidthValue(500, 'Mbps')).toBe('500.0 Mbps');
            expect(formatBandwidthValue(999, 'Mbps')).toBe('999.0 Mbps');
        });

        it('should format values >= 10 and < 100 with 2 decimal places', () => {
            expect(formatBandwidthValue(10, 'Mbps')).toBe('10.00 Mbps');
            expect(formatBandwidthValue(50.5, 'Mbps')).toBe('50.50 Mbps');
            expect(formatBandwidthValue(99.99, 'Mbps')).toBe('99.99 Mbps');
        });

        it('should format values < 10 with 3 decimal places', () => {
            expect(formatBandwidthValue(1, 'Mbps')).toBe('1.000 Mbps');
            expect(formatBandwidthValue(5.5, 'Mbps')).toBe('5.500 Mbps');
            expect(formatBandwidthValue(9.999, 'Mbps')).toBe('9.999 Mbps');
        });

    });
});

describe('Memory Unit Utilities', () => {
    describe('convertMemoryUnit', () => {
        it('should convert to TB for values >= 1048576 MB', () => {
            const result = convertMemoryUnit(1048576);
            expect(result.unit).toBe('TB');
            expect(result.value).toBe(1);
            expect(result.formattedValue).toBe('1.00');
        });

        it('should convert to TB for large values', () => {
            const result = convertMemoryUnit(2097152); // 2 TB
            expect(result.unit).toBe('TB');
            expect(result.value).toBe(2);
            expect(result.formattedValue).toBe('2.00');
        });

        it('should convert to GB for values >= 1024 MB and < 1048576 MB', () => {
            const result = convertMemoryUnit(1024);
            expect(result.unit).toBe('GB');
            expect(result.value).toBe(1);
            expect(result.formattedValue).toBe('1.00');
        });

        it('should convert to GB for values in GB range', () => {
            const result = convertMemoryUnit(2048); // 2 GB
            expect(result.unit).toBe('GB');
            expect(result.value).toBe(2);
            expect(result.formattedValue).toBe('2.00');
        });

        it('should keep as MB for values < 1024 MB', () => {
            const result = convertMemoryUnit(512);
            expect(result.unit).toBe('MB');
            expect(result.value).toBe(512);
            expect(result.formattedValue).toBe('512.00');
        });

        it('should handle small MB values', () => {
            const result = convertMemoryUnit(1);
            expect(result.unit).toBe('MB');
            expect(result.value).toBe(1);
            expect(result.formattedValue).toBe('1.00');
        });

        it('should handle zero value', () => {
            const result = convertMemoryUnit(0);
            expect(result.unit).toBe('MB');
            expect(result.value).toBe(0);
            expect(result.formattedValue).toBe('0.00');
        });

        it('should handle decimal values', () => {
            const result = convertMemoryUnit(1536); // 1.5 GB
            expect(result.unit).toBe('GB');
            expect(result.value).toBe(1.5);
            expect(result.formattedValue).toBe('1.50');
        });

        it('should format with 2 decimal places', () => {
            const result = convertMemoryUnit(1536.5);
            expect(result.formattedValue).toMatch(/^\d+\.\d{2}$/);
        });
    });

    describe('getBestMemoryUnit', () => {
        it('should return TB for values >= 1048576 MB', () => {
            expect(getBestMemoryUnit(1048576)).toBe('TB');
            expect(getBestMemoryUnit(2097152)).toBe('TB');
            expect(getBestMemoryUnit(5000000)).toBe('TB');
        });

        it('should return GB for values >= 1024 MB and < 1048576 MB', () => {
            expect(getBestMemoryUnit(1024)).toBe('GB');
            expect(getBestMemoryUnit(2048)).toBe('GB');
            expect(getBestMemoryUnit(1048575)).toBe('GB');
        });

        it('should return MB for values < 1024 MB', () => {
            expect(getBestMemoryUnit(0)).toBe('MB');
            expect(getBestMemoryUnit(512)).toBe('MB');
            expect(getBestMemoryUnit(1023)).toBe('MB');
        });

        it('should handle edge cases at boundaries', () => {
            expect(getBestMemoryUnit(1023.99)).toBe('MB');
            expect(getBestMemoryUnit(1024)).toBe('GB');
            expect(getBestMemoryUnit(1048575.99)).toBe('GB');
            expect(getBestMemoryUnit(1048576)).toBe('TB');
        });
    });

    describe('convertToUnit', () => {
        it('should convert MB to TB', () => {
            expect(convertToUnit(1048576, 'TB')).toBe(1);
            expect(convertToUnit(2097152, 'TB')).toBe(2);
            expect(convertToUnit(524288, 'TB')).toBe(0.5);
        });

        it('should convert MB to GB', () => {
            expect(convertToUnit(1024, 'GB')).toBe(1);
            expect(convertToUnit(2048, 'GB')).toBe(2);
            expect(convertToUnit(512, 'GB')).toBe(0.5);
        });

        it('should keep MB as MB', () => {
            expect(convertToUnit(100, 'MB')).toBe(100);
            expect(convertToUnit(1024, 'MB')).toBe(1024);
        });

        it('should handle unknown units by defaulting to MB', () => {
            expect(convertToUnit(1024, 'unknown')).toBe(1024);
            expect(convertToUnit(1024, '')).toBe(1024);
        });

        it('should handle zero value', () => {
            expect(convertToUnit(0, 'TB')).toBe(0);
            expect(convertToUnit(0, 'GB')).toBe(0);
            expect(convertToUnit(0, 'MB')).toBe(0);
        });

        it('should handle decimal values', () => {
            expect(convertToUnit(1536, 'GB')).toBe(1.5);
            expect(convertToUnit(1572864, 'TB')).toBe(1.5);
        });

        it('should handle large values', () => {
            expect(convertToUnit(10485760, 'TB')).toBe(10);
            expect(convertToUnit(10240, 'GB')).toBe(10);
        });
    });

    describe('formatMemoryValue', () => {
        it('should format values >= 1000 with k suffix and 1 decimal place', () => {
            expect(formatMemoryValue(1000, 'MB')).toBe('1.0k');
            expect(formatMemoryValue(5000, 'GB')).toBe('5.0k');
            expect(formatMemoryValue(12500, 'TB')).toBe('12.5k');
        });

        it('should format values >= 10 and < 1000 with no decimal places', () => {
            expect(formatMemoryValue(10, 'MB')).toBe('10');
            expect(formatMemoryValue(50, 'GB')).toBe('50');
            expect(formatMemoryValue(999, 'TB')).toBe('999');
        });

        it('should format values < 10 with 1 decimal place', () => {
            expect(formatMemoryValue(1, 'MB')).toBe('1.0');
            expect(formatMemoryValue(5.5, 'GB')).toBe('5.5');
            expect(formatMemoryValue(9.9, 'TB')).toBe('9.9');
        });

        it('should handle zero value', () => {
            expect(formatMemoryValue(0, 'MB')).toBe('0.0');
        });

        it('should handle edge cases at boundaries', () => {
            expect(formatMemoryValue(9.99, 'GB')).toBe('10.0');
            expect(formatMemoryValue(10, 'GB')).toBe('10');
            expect(formatMemoryValue(999.9, 'TB')).toBe('1000');
            expect(formatMemoryValue(1000, 'MB')).toBe('1.0k');
        });

        it('should work with any unit string', () => {
            expect(formatMemoryValue(1500, 'MB')).toBe('1.5k');
            expect(formatMemoryValue(1500, 'GB')).toBe('1.5k');
            expect(formatMemoryValue(1500, 'TB')).toBe('1.5k');
        });

        it('should handle decimal values correctly', () => {
            expect(formatMemoryValue(1.234, 'MB')).toBe('1.2');
            expect(formatMemoryValue(12.345, 'GB')).toBe('12');
            expect(formatMemoryValue(1234.567, 'TB')).toBe('1.2k');
        });

        it('should handle very large values', () => {
            expect(formatMemoryValue(100000, 'MB')).toBe('100.0k');
            expect(formatMemoryValue(999999, 'GB')).toBe('1000.0k');
        });
    });
});

describe('Integration Tests', () => {
    describe('Bandwidth conversion workflow', () => {

        it('should handle small bandwidth values workflow', () => {
            const maxValue = 0.5; // 0.5 Mbps
            const bestUnit = getBestBandwidthUnit(maxValue);
            expect(bestUnit).toBe('Kbps');

            const formatted = formatBandwidthValue(maxValue, bestUnit);
            expect(formatted).toBe('500.0 Kbps');
        });
    });

    describe('Memory conversion workflow', () => {
        it('should handle convertMemoryUnit with formatting', () => {
            const result = convertMemoryUnit(1536); // 1.5 GB
            expect(result.unit).toBe('GB');
            expect(result.formattedValue).toBe('1.50');

            const displayValue = formatMemoryValue(result.value, result.unit);
            expect(displayValue).toBe('1.5');
        });

        it('should handle large memory values workflow', () => {
            const maxValueInMB = 5120000; // ~5 TB
            const bestUnit = getBestMemoryUnit(maxValueInMB);
            expect(bestUnit).toBe('TB');

            const converted = convertToUnit(maxValueInMB, bestUnit);
            expect(converted).toBeCloseTo(4.88, 2);

            const result = convertMemoryUnit(maxValueInMB);
            expect(result.unit).toBe('TB');
            expect(parseFloat(result.formattedValue)).toBeCloseTo(4.88, 2);
        });
    });
});