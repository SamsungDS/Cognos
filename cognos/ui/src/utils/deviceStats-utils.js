import * as constants from '../constant';
// Color mapping for metrics
export const metricColors = {
    'CXL CAPACITY': '#FFB546',
    'CXL USAGE': '#0077C8',
    'CXL BANDWIDTH': '#00C3B2',
    'CXL TEMPERATURE': '#a30b0bff'
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
export const formatYAxisNumber = (value) => {
    const absValue = Math.abs(value);
    if (absValue >= 1e9) {
        return (value / 1e9).toFixed(1) + 'B';
    } else if (absValue >= 1e6) {
        return (value / 1e6).toFixed(1) + 'M';
    } else if (absValue >= 1e3) {
        return (value / 1e3).toFixed(1) + 'K';
    }
    return value.toString();
};
/**
 * Determines the best bandwidth unit based on the maximum value
 * @param {number} maxValue - Maximum bandwidth value in base unit (Mbps)
 * @returns {string} Best unit for display
 */
export const getBestBandwidthUnit = (maxValue) => {
    if (maxValue >= 1000) return 'Gbps';
    if (maxValue >= 1) return 'Mbps';
    if (maxValue >= 0.001) return 'Kbps';
    return 'bps';
};

/**
 * Converts bandwidth value from base unit to target unit
 * @param {number} value - Value in base unit
 * @param {string} targetUnit - Target unit (bps, Kbps, Mbps, Gbps)
 * @param {string} baseUnit - Base unit (default: Mbps)
 * @returns {number} Converted value
 */
export const convertBandwidthToUnit = (value, targetUnit, baseUnit = 'Mbps') => {
    // First convert to bps (base)
    let valueInBps = value;

    switch (baseUnit) {
        case 'Gbps':
            valueInBps = value * 1000000000;
            break;
        case 'Mbps':
            valueInBps = value * 1000000;
            break;
        case 'Kbps':
            valueInBps = value * 1000;
            break;
        case 'bps':
            valueInBps = value;
            break;
        default:
            valueInBps = value * 1000000; // Default to Mbps
    }

    // Then convert from bps to target unit
    switch (targetUnit) {
        case 'Gbps':
            return valueInBps / 1000000000;
        case 'Mbps':
            return valueInBps / 1000000;
        case 'Kbps':
            return valueInBps / 1000;
        case 'bps':
            return valueInBps;
        default:
            return valueInBps / 1000000; // Default to Mbps
    }
};

/**
 * Formats bandwidth value with appropriate unit
 * @param {number} value - Value in base unit
 * @param {string} targetUnit - Target unit for display
 * @param {string} baseUnit - Base unit (default: Mbps)
 * @returns {string} Formatted string with unit
 */
export const formatBandwidthValue = (value, targetUnit, baseUnit = 'Mbps') => {
    const converted = convertBandwidthToUnit(value, targetUnit, baseUnit);

    if (converted >= 1000) {
        return `${converted.toFixed(2)} ${targetUnit}`;
    } else if (converted >= 100) {
        return `${converted.toFixed(1)} ${targetUnit}`;
    } else if (converted >= 10) {
        return `${converted.toFixed(2)} ${targetUnit}`;
    } else {
        return `${converted.toFixed(3)} ${targetUnit}`;
    }
};
/**
 * Convert memory value to appropriate unit (MB, GB, TB)
 * @param {number} valueInMB - Memory value in MB
 * @returns {object} - { value, unit, formattedValue }
 */
export const convertMemoryUnit = (valueInMB) => {
    const TB_THRESHOLD = 1024 * 1024; // 1 TB in MB
    const GB_THRESHOLD = 1024; // 1 GB in MB

    if (valueInMB >= TB_THRESHOLD) {
        const valueInTB = valueInMB / TB_THRESHOLD;
        return {
            value: valueInTB,
            unit: 'TB',
            formattedValue: valueInTB.toFixed(2)
        };
    } else if (valueInMB >= GB_THRESHOLD) {
        const valueInGB = valueInMB / GB_THRESHOLD;
        return {
            value: valueInGB,
            unit: 'GB',
            formattedValue: valueInGB.toFixed(2)
        };
    } else {
        return {
            value: valueInMB,
            unit: 'MB',
            formattedValue: valueInMB.toFixed(2)
        };
    }
};

/**
 * Determine the best unit for a dataset based on max value
 * @param {number} maxValueInMB - Maximum value in the dataset (in MB)
 * @returns {string} - 'MB', 'GB', or 'TB'
 */
export const getBestMemoryUnit = (maxValueInMB) => {
    const TB_THRESHOLD = 1024 * 1024;
    const GB_THRESHOLD = 1024;

    if (maxValueInMB >= TB_THRESHOLD) return 'TB';
    if (maxValueInMB >= GB_THRESHOLD) return 'GB';
    return 'MB';
};

/**
 * Convert value from MB to target unit
 * @param {number} valueInMB - Value in MB
 * @param {string} targetUnit - 'MB', 'GB', or 'TB'
 * @returns {number} - Converted value
 */
export const convertToUnit = (valueInMB, targetUnit) => {
    switch (targetUnit) {
        case 'TB':
            return valueInMB / (1024 * 1024);
        case 'GB':
            return valueInMB / 1024;
        case 'MB':
        default:
            return valueInMB;
    }
};

/**
 * Format Y-axis number with appropriate memory unit
 * @param {number} value - Value to format
 * @param {string} unit - 'MB', 'GB', or 'TB'
 * @returns {string} - Formatted string
 */
export const formatMemoryValue = (value, unit) => {
    if (value >= 1000) {
        return `${(value / 1000).toFixed(1)}k`;
    }
    return value.toFixed(value < 10 ? 1 : 0);
};