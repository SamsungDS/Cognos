import * as constants from '../constant';
// Color mapping for metrics
export const metricColors = {
    'CXL Capacity': '#FFB546',
    'CXL Usage': '#0077C8',
    'CXL Bandwidth': '#00C3B2'
};

// Time filter configuration
// Temporarily disabled - will be re-enabled once API supports time filtering
export const TIME_FILTERS = [
    // { key: '3h', label: '3H' },
    // { key: '12h', label: '12H' },
    // { key: '1day', label: '1 Day' },
    // { key: '7day', label: '7 Days' }
];

// Flag to control time filter visibility in UI
export const ENABLE_TIME_FILTER = false;

// Stat key mapping for different metrics
export const STAT_KEYS = {
    capacity: 'cxl_capacity',
    usage: 'cxl_usage',
    bandwidth: 'cxl_bandwidth',
    temperature: 'fpga_temp_in_F'
};

// API Configuration
export const API_CONFIG = {
    USE_MOCK: true, // Set to false when actual API is ready
    BASE_URL: constants.Configs.api_endpoint,
    ENDPOINTS: {
        TOPOLOGY: '/topology',
        DEVICE_STATS: '/device_stats'
    }
};

// API Service Layer
export const apiService = {
    // Fetch topology data (clusters, nodes, devices hierarchy)
    async fetchTopology() {
        if (API_CONFIG.USE_MOCK) {
            return this.mockFetchTopology();
        }

        try {
            const response = await fetch(`${API_CONFIG.BASE_URL}${API_CONFIG.ENDPOINTS.TOPOLOGY}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    // Add authentication headers if needed
                    // 'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                throw new Error(`API Error: ${response.status}`);
            }

            const data = await response.json();
            return this.parseTopologyResponse(data);
        } catch (error) {
            console.error('Error fetching topology:', error);
            throw error;
        }
    },

    // Transform actual API response to expected format
    parseTopologyResponse(apiResponse) {
        if (!apiResponse || !apiResponse.clusters) {
            return [];
        }

        return apiResponse.clusters.map((cluster, clusterIndex) => {
            // Group nodes by node_name to handle duplicates
            const nodeMap = new Map();

            cluster.nodes.forEach((node, nodeIndex) => {
                const nodeName = node.node_name;

                if (!nodeMap.has(nodeName)) {
                    nodeMap.set(nodeName, {
                        id: nodeName,
                        name: nodeName,
                        devices: [],
                        fm_type: node.fm_type
                    });
                }

                // Add devices from this node entry
                const nodeData = nodeMap.get(nodeName);
                node.devices.forEach((deviceName, deviceIndex) => {
                    nodeData.devices.push({
                        id: deviceName,
                        name: deviceName,
                        fm_type: node.fm_type
                    });
                });
            });

            return {
                id: cluster.cluster_name,
                name: cluster.cluster_name,
                nodes: Array.from(nodeMap.values())
            };
        });
    },

    // Alias for backward compatibility
    async fetchClusters() {
        return this.fetchTopology();
    },

    // Fetch device stats for a specific metric
    async fetchDeviceStats(deviceId, statKey) {
        if (API_CONFIG.USE_MOCK) {
            return this.mockFetchDeviceStats(deviceId, statKey);
        }

        try {
            const response = await fetch(
                `${API_CONFIG.BASE_URL}${API_CONFIG.ENDPOINTS.DEVICE_STATS}`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        device_id: deviceId,
                        stat_key: statKey
                    })
                }
            );

            if (!response.ok) {
                throw new Error(`API Error: ${response.status}`);
            }

            const data = await response.json();
            return this.parseDeviceStatsResponse(data, deviceId);
        } catch (error) {
            console.error('Error fetching device stats:', error);
            throw error;
        }
    },

    // Fetch metrics data for a specific device (fetches all required metrics)
    // timeFilter parameter kept for backward compatibility but not used currently
    async fetchMetrics(deviceId, timeFilter = null) {
        if (API_CONFIG.USE_MOCK) {
            return this.mockFetchMetrics(deviceId, timeFilter);
        }

        try {
            // Fetch all three metrics in parallel
            // Note: timeFilter is not passed to API as it's currently disabled
            const [capacityData, usageData, bandwidthData] = await Promise.all([
                this.fetchDeviceStats(deviceId, STAT_KEYS.capacity),
                this.fetchDeviceStats(deviceId, STAT_KEYS.usage),
                this.fetchDeviceStats(deviceId, STAT_KEYS.bandwidth)
            ]);

            return {
                capacity: capacityData,
                usage: usageData,
                bandwidth: bandwidthData
            };
        } catch (error) {
            console.error('Error fetching metrics:', error);
            throw error;
        }
    },

    // Parse the API response format: { 'device_id': [[ts, key, value], ...] }
    parseDeviceStatsResponse(response, deviceId) {
        const deviceData = response[deviceId];

        if (!deviceData || !Array.isArray(deviceData)) {
            return [];
        }

        // Transform [[ts, key, value], ...] to [{ time, value }, ...]
        return deviceData.map(([timestamp, key, value]) => ({
            time: this.formatTimestamp(timestamp),
            value: parseFloat(value) || 0
        }));
    },

    // Format timestamp based on your time display needs
    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        // Customize format as needed
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
    },

    // Mock implementation for development
    mockFetchTopology() {
        return new Promise((resolve) => {
            setTimeout(() => {
                // Mock data mimicking actual API response structure
                const mockApiResponse = {
                    clusters: [
                        {
                            cluster_name: 'CL_ID_1',
                            nodes: [
                                {
                                    node_name: 'node_1',
                                    devices: ['DEV14-256G', 'DEV15-256G'],
                                    fm_type: 'FM_DIRECT_CMMD'
                                },
                                {
                                    node_name: 'node_1',
                                    devices: ['DEV17-256G'],
                                    fm_type: 'FM_DIRECT_CMMH'
                                }
                            ]
                        },
                        {
                            cluster_name: 'CL_ID_2',
                            nodes: [
                                {
                                    node_name: 'node_2',
                                    devices: ['DEV18-512G', 'DEV19-512G'],
                                    fm_type: 'FM_DIRECT_CMMD'
                                }
                            ]
                        }
                    ]
                };

                // Transform to expected output format
                resolve(this.parseTopologyResponse(mockApiResponse));
            }, 1000);
        });
    },

    mockFetchDeviceStats(deviceId, statKey) {
        return new Promise((resolve) => {
            setTimeout(() => {
                const now = Date.now();
                const dataPoints = 7;
                const intervalMs = 30 * 60 * 1000; // 30 minutes

                // Generate mock data in the API response format
                const mockData = {
                    [deviceId]: Array.from({ length: dataPoints }, (_, i) => {
                        const timestamp = now - (dataPoints - 1 - i) * intervalMs;
                        const baseValue = Math.random() * 50 + 25;
                        return [
                            timestamp,
                            statKey,
                            (baseValue + (Math.random() - 0.5) * 20).toFixed(2)
                        ];
                    })
                };

                resolve(this.parseDeviceStatsResponse(mockData, deviceId));
            }, 500);
        });
    },

    mockFetchMetrics(deviceId, timeFilter) {
        return new Promise((resolve) => {
            setTimeout(() => {
                const baseCapacity = Math.random() * 15 + 75;
                const baseUsage = Math.random() * 20 + 45;
                const baseBandwidth = Math.random() * 15 + 15;

                let times = [];

                switch (timeFilter) {
                    case '3h':
                        times = ['00:00', '00:30', '01:00', '01:30', '02:00', '02:30', '03:00'];
                        break;
                    case '12h':
                        times = ['00:00', '02:00', '04:00', '06:00', '08:00', '10:00', '12:00'];
                        break;
                    case '1day':
                        times = ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'];
                        break;
                    case '7day':
                        times = ['Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5', 'Day 6', 'Day 7'];
                        break;
                    default:
                        times = ['00:00', '00:30', '01:00', '01:30', '02:00', '02:30', '03:00'];
                }

                resolve({
                    capacity: times.map(time => ({
                        time,
                        value: Math.max(0, Math.min(100, baseCapacity + (Math.random() - 0.5) * 10))
                    })),
                    usage: times.map(time => ({
                        time,
                        value: Math.max(0, Math.min(100, baseUsage + (Math.random() - 0.5) * 15))
                    })),
                    bandwidth: times.map(time => ({
                        time,
                        value: Math.max(0, Math.min(100, baseBandwidth + (Math.random() - 0.5) * 12))
                    }))
                });
            }, 500);
        });
    }
};

export const getMarginForTimeFilter = (filter, containerWidth) => {
    const baseBottom = containerWidth < 400 ? 70 : 60;
    switch (filter) {
        case '3h':
        case '12h':
            return { top: 20, right: 30, bottom: baseBottom + 10, left: 50 };
        case '1day':
            return { top: 20, right: 30, bottom: baseBottom + 10, left: 50 };
        case '7day':
            return { top: 20, right: 30, bottom: baseBottom, left: 50 };
        default:
            return { top: 20, right: 30, bottom: baseBottom + 10, left: 50 };
    }
};