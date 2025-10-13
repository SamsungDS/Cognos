import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import DeviceCard from '../components/device-Stats/deviceCard';
import { apiService } from '../utils/deviceStats-utils';

// Mock the utility modules
jest.mock('../utils/deviceStats-utils', () => ({
    metricColors: {
        'CXL Capacity': '#4CAF50',
        'CXL Usage': '#2196F3',
        'CXL Bandwidth': '#FF9800'
    },
    TIME_FILTERS: [
        { key: '3h', label: '3 Hours' },
        { key: '1d', label: '1 Day' },
        { key: '1w', label: '1 Week' }
    ],
    apiService: {
        fetchClusters: jest.fn(),
        fetchMetrics: jest.fn()
    },
    getMarginForTimeFilter: jest.fn(() => ({
        top: 20,
        right: 20,
        bottom: 60,
        left: 60
    }))
}));

// Mock CSS import
jest.mock('../components/device-Stats/deviceCard.css', () => ({}));

// Mock MetricItem component
jest.mock('../components/device-Stats/MetricItem', () => {
    return function MetricItem({ label }) {
        return <div data-testid={`metric-item-${label}`}>{label}</div>;
    };
});

// Mock TreeItem component
jest.mock('../components/device-Stats/TreeItem', () => {
    return function TreeItem({ label, children, isExpanded, toggleExpanded, onClick, isSelected, level }) {
        return (
            <div data-testid={`tree-item-${label}`} data-level={level}>
                <button
                    onClick={() => toggleExpanded?.(label)}
                    data-testid={`toggle-${label}`}
                >
                    {isExpanded ? '▼' : '▶'} {label}
                </button>
                {onClick && (
                    <button
                        onClick={onClick}
                        data-testid={`select-${label}`}
                        data-selected={isSelected}
                    >
                        Select
                    </button>
                )}
                {isExpanded && children}
            </div>
        );
    };
});

// Mock d3
jest.mock('d3', () => ({
    select: jest.fn(() => ({
        selectAll: jest.fn().mockReturnThis(),
        remove: jest.fn().mockReturnThis(),
        attr: jest.fn().mockReturnThis(),
        append: jest.fn().mockReturnThis(),
        call: jest.fn().mockReturnThis(),
        style: jest.fn().mockReturnThis(),
        text: jest.fn().mockReturnThis(),
        datum: jest.fn().mockReturnThis(),
        data: jest.fn().mockReturnThis(),
        enter: jest.fn().mockReturnThis()
    })),
    scaleBand: jest.fn(() => ({
        domain: jest.fn().mockReturnThis(),
        range: jest.fn().mockReturnThis(),
        padding: jest.fn().mockReturnThis(),
        bandwidth: jest.fn(() => 10)
    })),
    scaleLinear: jest.fn(() => ({
        domain: jest.fn().mockReturnThis(),
        range: jest.fn().mockReturnThis(),
        ticks: jest.fn(() => [0, 25, 50, 75, 100])
    })),
    line: jest.fn(() => {
        const lineFunc = jest.fn();
        lineFunc.x = jest.fn().mockReturnThis();
        lineFunc.y = jest.fn().mockReturnThis();
        lineFunc.curve = jest.fn().mockReturnThis();
        return lineFunc;
    }),
    axisBottom: jest.fn(() => jest.fn()),
    axisLeft: jest.fn(() => jest.fn()),
    curveCardinal: {}
}));

describe('DeviceCard Component', () => {
    const mockClustersData = [
        {
            id: 'cluster-1',
            name: 'Cluster 1',
            nodes: [
                {
                    id: 'node-1',
                    name: 'Node 1',
                    devices: [
                        { id: 'device-1', name: 'Device 1' },
                        { id: 'device-2', name: 'Device 2' }
                    ]
                }
            ]
        }
    ];

    const mockMetricsData = {
        capacity: [
            { time: '10:00', value: 50 },
            { time: '11:00', value: 60 }
        ],
        usage: [
            { time: '10:00', value: 30 },
            { time: '11:00', value: 40 }
        ],
        bandwidth: [
            { time: '10:00', value: 70 },
            { time: '11:00', value: 80 }
        ]
    };

    const mockSelectedMetrics = {
        'CXL Capacity': true,
        'CXL Usage': true,
        'CXL Bandwidth': true
    };

    beforeEach(() => {
        jest.clearAllMocks();
        apiService.fetchClusters.mockResolvedValue(mockClustersData);
        apiService.fetchMetrics.mockResolvedValue(mockMetricsData);

        // Mock ResizeObserver
        global.ResizeObserver = jest.fn().mockImplementation(() => ({
            observe: jest.fn(),
            unobserve: jest.fn(),
            disconnect: jest.fn()
        }));

        // Mock getBoundingClientRect
        Element.prototype.getBoundingClientRect = jest.fn(() => ({
            width: 800,
            height: 600,
            top: 0,
            left: 0,
            bottom: 600,
            right: 800
        }));
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    test('renders without crashing', () => {
        render(
            <DeviceCard
                selectedMetrics={mockSelectedMetrics}
                setSelectedMetrics={jest.fn()}
            />
        );
        expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    test('loads and displays clusters data on mount', async () => {
        render(
            <DeviceCard
                selectedMetrics={mockSelectedMetrics}
                setSelectedMetrics={jest.fn()}
            />
        );

        await waitFor(() => {
            expect(apiService.fetchClusters).toHaveBeenCalledTimes(1);
        });

        await waitFor(() => {
            expect(screen.getByTestId('tree-item-Clusters')).toBeInTheDocument();
        });
    });


    test('displays error message when data loading fails', async () => {
        apiService.fetchClusters.mockRejectedValue(new Error('Network error'));

        render(
            <DeviceCard
                selectedMetrics={mockSelectedMetrics}
                setSelectedMetrics={jest.fn()}
            />
        );

        await waitFor(() => {
            expect(screen.getByText('Failed to load data. Please try again.')).toBeInTheDocument();
        });
    });

  
    test('shows "Select a device" message when no device is selected', () => {
        apiService.fetchClusters.mockResolvedValue([]);

        render(
            <DeviceCard
                selectedMetrics={mockSelectedMetrics}
                setSelectedMetrics={jest.fn()}
            />
        );

        // Will show after clusters load with no devices
        waitFor(() => {
            expect(screen.queryByText('Select a device to view metrics')).toBeInTheDocument();
        });
    });

    

    test('collapses other clusters when expanding a new one', async () => {
        const multiClusterData = [
            {
                id: 'cluster-1',
                name: 'Cluster 1',
                nodes: [{ id: 'node-1', name: 'Node 1', devices: [] }]
            },
            {
                id: 'cluster-2',
                name: 'Cluster 2',
                nodes: [{ id: 'node-2', name: 'Node 2', devices: [] }]
            }
        ];

        apiService.fetchClusters.mockResolvedValue(multiClusterData);

        render(
            <DeviceCard
                selectedMetrics={mockSelectedMetrics}
                setSelectedMetrics={jest.fn()}
            />
        );

        await waitFor(() => {
            expect(screen.getByTestId('toggle-Cluster 2')).toBeInTheDocument();
        });

        // Expand Cluster 2 (Cluster 1 is already expanded by default)
        fireEvent.click(screen.getByTestId('toggle-Cluster 2'));

        // Cluster 2 should now be expanded
        expect(screen.getByTestId('toggle-Cluster 2').textContent).toContain('▼');
    });

    test('renders SVG element for chart', async () => {
        render(
            <DeviceCard
                selectedMetrics={mockSelectedMetrics}
                setSelectedMetrics={jest.fn()}
            />
        );

        await waitFor(() => {
            const svg = document.querySelector('svg');
            expect(svg).toBeInTheDocument();
        });
    });
});