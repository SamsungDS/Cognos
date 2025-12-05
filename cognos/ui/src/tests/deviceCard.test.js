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
        fetchDeviceStats: jest.fn()
    },
    getMarginForTimeFilter: jest.fn(() => ({
        top: 20,
        right: 20,
        bottom: 60,
        left: 60
    })),
    getBestMemoryUnit: jest.fn(() => 'MB'),
    convertToUnit: jest.fn((value) => value),
    getBestBandwidthUnit: jest.fn(() => 'Mbps'),
    convertBandwidthToUnit: jest.fn((value) => value)
}));

jest.mock('../components/device-Stats/deviceCard.css', () => ({}));

jest.mock('../components/device-Stats/MetricItem', () => {
    return function MetricItem({ label }) {
        return <div data-testid={`metric-item-${label}`}>{label}</div>;
    };
});

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

jest.mock('../components/device-Stats/YAxisConfigModal', () => {
    return function YAxisConfigModal({ isOpen, onClose, onSave, onReset }) {
        if (!isOpen) return null;
        return (
            <div data-testid="y-axis-modal">
                <div>Y-Axis Config Modal</div>
                <button onClick={() => onSave({ min: 0, max: 100 })} data-testid="modal-save">Save</button>
                <button onClick={onReset} data-testid="modal-reset">Reset</button>
                <button onClick={onClose} data-testid="modal-close">Close</button>
            </div>
        );
    };
});

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
        enter: jest.fn().mockReturnThis(),
        on: jest.fn().mockReturnThis(),
        each: jest.fn().mockReturnThis(),
        join: jest.fn().mockReturnThis(),
        html: jest.fn().mockReturnThis(),
        transition: jest.fn().mockReturnThis(),
        duration: jest.fn().mockReturnThis()
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
        nice: jest.fn().mockReturnThis(),
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
    axisLeft: jest.fn(() => ({
        ticks: jest.fn(() => jest.fn())
    })),
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
                },
                {
                    id: 'node-2',
                    name: 'Node 2',
                    devices: [
                        { id: 'device-3', name: 'Device 3' }
                    ]
                }
            ]
        }
    ];

    const mockMetricsData = [
        { time: '10:00', value: 50 },
        { time: '11:00', value: 60 },
        { time: '12:00', value: 55 }
    ];

    const mockSelectedMetrics = {
        'CXL Capacity': 'capacity',
        'CXL Usage': 'usage',
        'CXL Bandwidth': 'bandwidth'
    };

    let mockSetGlobalSelectedDevice;

    beforeEach(() => {
        jest.clearAllMocks();
        jest.useFakeTimers();

        mockSetGlobalSelectedDevice = jest.fn();

        apiService.fetchClusters.mockResolvedValue(mockClustersData);
        apiService.fetchDeviceStats.mockResolvedValue(mockMetricsData);

        global.ResizeObserver = jest.fn().mockImplementation(() => ({
            observe: jest.fn(),
            unobserve: jest.fn(),
            disconnect: jest.fn()
        }));

        Element.prototype.getBoundingClientRect = jest.fn(() => ({
            width: 800,
            height: 600,
            top: 0,
            left: 0,
            bottom: 600,
            right: 800
        }));

        global.requestAnimationFrame = jest.fn((cb) => {
            cb();
            return 1;
        });
    });

    afterEach(() => {
        jest.runOnlyPendingTimers();
        jest.useRealTimers();
        jest.restoreAllMocks();
    });

    const renderDeviceCard = (props = {}) => {
        return render(
            <DeviceCard
                selectedMetrics={mockSelectedMetrics}
                setSelectedMetrics={jest.fn()}
                globalSelectedDevice={null}
                setGlobalSelectedDevice={mockSetGlobalSelectedDevice}
                {...props}
            />
        );
    };

    test('renders without crashing', () => {
        renderDeviceCard();
        expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    test('loads and displays clusters data on mount', async () => {
        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
            jest.advanceTimersByTime(100);
        });

        await waitFor(() => {
            expect(apiService.fetchClusters).toHaveBeenCalledTimes(1);
        });

        await waitFor(() => {
            expect(screen.getByTestId('tree-item-Clusters')).toBeInTheDocument();
        }, { timeout: 3000 });
    });

    test('displays error message when data loading fails', async () => {
        apiService.fetchClusters.mockRejectedValue(new Error('Network error'));

        renderDeviceCard();

        await waitFor(() => {
            expect(screen.getByText('Failed to load data. Please try again.')).toBeInTheDocument();
        });
    });

    test('shows "Select a device" message when no device is selected', async () => {
        apiService.fetchClusters.mockResolvedValue([]);

        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
        });

        await waitFor(() => {
            expect(screen.getByText('Select a device to view metrics')).toBeInTheDocument();
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

        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
        });

        await waitFor(() => {
            expect(screen.getByTestId('toggle-Cluster 2')).toBeInTheDocument();
        });

        await act(async () => {
            fireEvent.click(screen.getByTestId('toggle-Cluster 2'));
        });

        expect(screen.getByTestId('toggle-Cluster 2').textContent).toContain('▼');
    });

    test('collapses node when collapsing its parent cluster', async () => {
        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
            jest.advanceTimersByTime(100);
        });

        await waitFor(() => {
            expect(screen.getByTestId('toggle-Cluster 1')).toBeInTheDocument();
        }, { timeout: 3000 });

        // Verify cluster is expanded by default
        expect(screen.getByTestId('toggle-Cluster 1').textContent).toContain('▼');

        // Collapse the cluster
        await act(async () => {
            fireEvent.click(screen.getByTestId('toggle-Cluster 1'));
        });

        expect(screen.getByTestId('toggle-Cluster 1').textContent).toContain('▶');
    });

    test('collapses other nodes when expanding a node in same cluster', async () => {
        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
            jest.advanceTimersByTime(100);
        });

        await waitFor(() => {
            expect(screen.getByTestId('toggle-Node 2')).toBeInTheDocument();
        }, { timeout: 3000 });

        // Node 1 should be expanded by default
        expect(screen.getByTestId('toggle-Node 1').textContent).toContain('▼');

        // Expand Node 2
        await act(async () => {
            fireEvent.click(screen.getByTestId('toggle-Node 2'));
        });

        // Node 2 should now be expanded
        expect(screen.getByTestId('toggle-Node 2').textContent).toContain('▼');
    });

    test('renders all metric items in sidebar', async () => {
        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
            jest.advanceTimersByTime(100);
        });

        await waitFor(() => {
            expect(screen.getByTestId('tree-item-Clusters')).toBeInTheDocument();
        }, { timeout: 3000 });

        await waitFor(() => {
            expect(screen.getByTestId('metric-item-CXL Capacity')).toBeInTheDocument();
            expect(screen.getByTestId('metric-item-CXL Usage')).toBeInTheDocument();
            expect(screen.getByTestId('metric-item-CXL Bandwidth')).toBeInTheDocument();
        });
    });

    test('handles ResizeObserver updates', async () => {
        let resizeCallback;
        global.ResizeObserver = jest.fn().mockImplementation((callback) => {
            resizeCallback = callback;
            return {
                observe: jest.fn(),
                unobserve: jest.fn(),
                disconnect: jest.fn()
            };
        });

        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
            jest.advanceTimersByTime(100);
        });

        await waitFor(() => {
            expect(screen.getByTestId('tree-item-Clusters')).toBeInTheDocument();
        });

        if (resizeCallback) {
            await act(async () => {
                resizeCallback([{
                    contentRect: { width: 900, height: 700 }
                }]);
            });
        }

        expect(screen.getByTestId('tree-item-Clusters')).toBeInTheDocument();
    });

    test('shows loading message for chart when dimensions are zero', async () => {
        Element.prototype.getBoundingClientRect = jest.fn(() => ({
            width: 0,
            height: 0,
            top: 0,
            left: 0,
            bottom: 0,
            right: 0
        }));

        const device = { id: 'device-1', name: 'Device 1' };

        renderDeviceCard({ globalSelectedDevice: device });

        await act(async () => {
            await Promise.resolve();
            jest.advanceTimersByTime(100);
        });

        await waitFor(() => {
            expect(screen.getByText('Loading chart...')).toBeInTheDocument();
        }, { timeout: 3000 });
    });

    test('handles clusters with no nodes', async () => {
        const emptyNodesData = [
            {
                id: 'cluster-1',
                name: 'Empty Cluster',
                nodes: []
            }
        ];

        apiService.fetchClusters.mockResolvedValue(emptyNodesData);

        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
        });

        await waitFor(() => {
            expect(screen.getByTestId('tree-item-Empty Cluster')).toBeInTheDocument();
        });
    });

    test('handles nodes with no devices', async () => {
        const noDevicesData = [
            {
                id: 'cluster-1',
                name: 'Cluster 1',
                nodes: [
                    {
                        id: 'node-1',
                        name: 'Empty Node',
                        devices: []
                    }
                ]
            }
        ];

        apiService.fetchClusters.mockResolvedValue(noDevicesData);

        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
        });

        await waitFor(() => {
            expect(screen.getByTestId('tree-item-Empty Node')).toBeInTheDocument();
        });
    });

    test('cleans up timers on unmount', async () => {
        const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');
        const clearIntervalSpy = jest.spyOn(global, 'clearInterval');

        const { unmount } = renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
        });

        await waitFor(() => {
            expect(apiService.fetchClusters).toHaveBeenCalled();
        });

        unmount();

        expect(clearTimeoutSpy).toHaveBeenCalled();
        expect(clearIntervalSpy).toHaveBeenCalled();
    });

    test('renders ErrorBanner component with correct message', async () => {
        apiService.fetchClusters.mockRejectedValue(new Error('Test error'));

        renderDeviceCard();

        await waitFor(() => {
            const errorBanner = screen.getByText('Failed to load data. Please try again.');
            expect(errorBanner).toBeInTheDocument();
            expect(errorBanner.closest('.error-banner')).toBeInTheDocument();
        });
    });

    test('renders Sidebar component correctly', async () => {
        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
        });

        await waitFor(() => {
            const sidebar = document.querySelector('.sidebar-device');
            expect(sidebar).toBeInTheDocument();
        });
    });

    test('renders ChartArea component correctly', async () => {
        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
        });

        await waitFor(() => {
            const chartArea = document.querySelector('.chart-area');
            expect(chartArea).toBeInTheDocument();
        });
    });

    test('handles metrics fetch error in initial load', async () => {
        apiService.fetchDeviceStats.mockRejectedValue(new Error('Metrics error'));

        const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
            jest.advanceTimersByTime(100);
        });

        await waitFor(() => {
            expect(consoleErrorSpy).toHaveBeenCalledWith(
                expect.stringContaining('Error fetching'),
                expect.any(Error)
            );
        }, { timeout: 3000 });

        consoleErrorSpy.mockRestore();
    });

    test('re-expands collapsed cluster', async () => {
        renderDeviceCard();

        await act(async () => {
            await Promise.resolve();
            jest.advanceTimersByTime(100);
        });

        await waitFor(() => {
            expect(screen.getByTestId('toggle-Cluster 1')).toBeInTheDocument();
        });

        // Collapse
        await act(async () => {
            fireEvent.click(screen.getByTestId('toggle-Cluster 1'));
        });
        expect(screen.getByTestId('toggle-Cluster 1').textContent).toContain('▶');

        // Re-expand
        await act(async () => {
            fireEvent.click(screen.getByTestId('toggle-Cluster 1'));
        });
        expect(screen.getByTestId('toggle-Cluster 1').textContent).toContain('▼');
    });

});