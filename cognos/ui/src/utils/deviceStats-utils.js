import * as constants from '../constant';
// Color mapping for metrics
export const metricColors = {
    'CXL Capacity': '#FFB546',
    'CXL Usage': '#0077C8',
    'CXL Bandwidth': '#00C3B2',
    'CXL Temperature': '#a30b0bff'
};

// Time filter configuration
export const TIME_FILTERS = [
    // { key: '3h', label: '3H' },
    // { key: '12h', label: '12H' },
    // { key: '1day', label: '1 Day' },
    // { key: '7day', label: '7 Days' }
];

// Flag to control time filter visibility in UI
export const ENABLE_TIME_FILTER = false;

// API Configuration
// istanbul ignore next
export const API_CONFIG = {
    BASE_URL: constants.Configs.api_endpoint,
    ENDPOINTS: {
        TOPOLOGY: '/topology',
        DEVICE_STATS: '/device_stats'
    }
};

// API Service Layer
// istanbul ignore next
export const apiService = {
    // Fetch topology data (clusters, nodes, devices hierarchy)
    async fetchTopology() {        
        try {
            const response = await fetch(`${API_CONFIG.BASE_URL}${API_CONFIG.ENDPOINTS.TOPOLOGY}`, {
                mode: "cors",
                method: "GET",
                headers: {
                    "Content-Type": "application/json",
                    accept: "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
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
        if (!apiResponse?.clusters) {
            return [];
        }

        return apiResponse.clusters.map((cluster, clusterIndex) => {
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

        try {
            const response = await fetch(
                `${API_CONFIG.BASE_URL}${API_CONFIG.ENDPOINTS.DEVICE_STATS}`,
                {
                    method: 'POST',
                    mode: "cors",
                    headers: {
                        "Content-Type": "application/json",
                        accept: "application/json",
                        "Access-Control-Allow-Origin": "*",
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

    // Parse the API response format: { 'device_id': [[ts, key, value], ...] }
    parseDeviceStatsResponse(response, deviceId) {
        const deviceData = response[deviceId];

        if (!deviceData || !Array.isArray(deviceData)) {
            return [];
        }

        return deviceData.map(([timestamp, key, value]) => ({
            time: this.formatTimestamp(timestamp),
            value: parseFloat(value) || 0
        }));
    },

    // Format timestamp based on your time display needs
    formatTimestamp(timestamp) {
        // Handle string format with colons (HH:MM or HH:MM:SS)
        if (typeof timestamp === 'string' && /^\d{1,2}:\d{2}(:\d{2})?$/.test(timestamp)) {
            const parts = timestamp.split(':');
            const hours = parts[0].padStart(2, '0');
            const minutes = parts[1];
            const seconds = parts[2] ? parts[2] : '00';
            return `${hours}:${minutes}:${seconds}`;
        }
        
        // Handle Date object or timestamp number
        const date = new Date(timestamp);
        if (isNaN(date.getTime())) {
            console.warn(`Invalid timestamp: ${timestamp}`);
            return timestamp;
        }
        
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

};

export const getMarginForTimeFilter = (filter, containerWidth) => {
    // istanbul ignore next
    const baseBottom = containerWidth < 400 ? 70 : 60;
    // istanbul ignore next
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