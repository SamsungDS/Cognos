import React from 'react';
import { render, screen } from '@testing-library/react';
import DeviceStats from '../pages/DeviceStats';

// Mock DeviceCard component
jest.mock('../components/device-Stats/deviceCard', () => {
    return jest.fn(({ selectedMetrics }) => (
        <div data-testid="mock-device-card">
            {Object.keys(selectedMetrics).join(', ')}
        </div>
    ));
});

describe('DeviceStats Component', () => {
    test('passes correct props to each DeviceCard', () => {
        // Import the mocked component to inspect calls
        const DeviceCard = require('../components/device-Stats/deviceCard');
        render(<DeviceStats />);

        // Verify DeviceCard called 4 times
        expect(DeviceCard).toHaveBeenCalledTimes(4);

        // Check props for first DeviceCard
        expect(DeviceCard.mock.calls[0][0].selectedMetrics).toEqual({
            'CXL Capacity': 'total_memory_MB',
            
        });
    });

});
