import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import PropTypes from 'prop-types';
import './deviceCard.css';
import MetricItem from './MetricItem';
import TreeItem from './TreeItem';
import YAxisConfigModal from './YAxisConfigModal';
import {
    metricColors, apiService, getMarginForTimeFilter,
    getBestMemoryUnit,
    convertToUnit,  
    getBestBandwidthUnit,
    convertBandwidthToUnit,
} from '../../utils/deviceStats-utils';

const DeviceCard = ({ selectedMetrics, setSelectedMetrics }) => {
    const svgRef = useRef();
    const containerRef = useRef();

    const [expandedItems, setExpandedItems] = useState({});
    const [selectedDevice, setSelectedDevice] = useState(null);
    const [clustersData, setClustersData] = useState([]);
    const [metricsData, setMetricsData] = useState({});
    const [loading, setLoading] = useState(true);
    const [timeFilter, setTimeFilter] = useState('3h');
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
    const [error, setError] = useState(null);
    const [yAxisConfig, setYAxisConfig] = useState({ min: null, max: null, unit: null });
    const [showYAxisModal, setShowYAxisModal] = useState(false);

    // Helper function to determine metric type and available units
    // istanbul ignore next
    const getMetricInfo = useCallback((metricKey) => {
        if (!metricKey) return { type: 'memory', units: ['Bytes', 'KB', 'MB', 'GB', 'TB'], baseUnit: 'MB' };

        const key = metricKey.toLowerCase();

        if (key.includes('temp')) {
            return {
                type: 'temperature',
                units: ['°F', '°C'],
                baseUnit: key.includes('_f') ? '°F' : '°C',
                suffix: key.includes('_f') ? '°F' : '°C'
            };
        } else if (key.includes('bandwidth') || key.includes('bps')) {
            return {
                type: 'bandwidth',
                units: ['bps', 'Kbps', 'Mbps', 'Gbps'],
                baseUnit: 'Mbps',
                suffix: 'bps'
            };
        } else if (key.includes('memory') || key.includes('mem')) {
            return {
                type: 'memory',
                units: ['Bytes', 'KB', 'MB', 'GB', 'TB'],
                baseUnit: 'MB',
                suffix: 'B'
            };
        } else {
            // Default to generic numeric
            return {
                type: 'generic',
                units: ['Value'],
                baseUnit: 'Value',
                suffix: ''
            };
        }
    }, []);

    const updateDimensions = useCallback(() => {
        if (containerRef.current) {
            const rect = containerRef.current.getBoundingClientRect();
            const newDimensions = {
                width: rect.width,
                height: rect.height
            };

            setDimensions(prev => {
                if (prev.width !== newDimensions.width || prev.height !== newDimensions.height) {
                    return newDimensions;
                }
                return prev;
            });
        }
    }, []);

    useEffect(() => {
        if (selectedDevice) {
            const timer = setTimeout(updateDimensions, 100);
            return () => clearTimeout(timer);
        }
    }, [selectedDevice, updateDimensions]);

    useEffect(() => {
        let intervalId;

        const loadData = async () => {
            setLoading(true);
            setError(null);

            try {
                const clusters = await apiService.fetchClusters();
                setClustersData(clusters);

                const initialExpanded = { 'Clusters': true };

                if (clusters?.length > 0) {
                    const firstCluster = clusters[0];
                    initialExpanded[firstCluster.name] = true;

                    if (firstCluster.nodes?.length > 0) {
                        const firstNode = firstCluster.nodes[0];
                        initialExpanded[firstNode.name] = true;

                        if (firstNode.devices?.length > 0) {
                            const firstDevice = firstNode.devices[0];
                            setSelectedDevice(firstDevice);

                            // Wait for next render cycle to ensure selectedDevice state is updated
                            // Then start polling with the correct device
                            setTimeout(() => {
                                startMetricsPolling(firstDevice);
                            }, 0);
                        }
                    }
                }

                setExpandedItems(initialExpanded);
            } catch (err) {
                setError('Failed to load data. Please try again.');
                console.error('Load data error:', err);
            } finally {
                setLoading(false);
            }
        };

        const startMetricsPolling = (device) => {
            // Clear any existing interval
            if (intervalId) {
                clearInterval(intervalId);
            }

            const fetchMetricsData = async () => {
                if (!device?.id || !selectedMetrics) {
                    return;
                }

                try {
                    const activeMetrics = Object.entries(selectedMetrics)
                        .filter(([_, value]) => value);

                    if (activeMetrics.length === 0) {
                        return;
                    }

                    const metricsPromises = activeMetrics.map(([key, metricKey]) =>
                        apiService.fetchDeviceStats(device.id, metricKey)
                            .then(data => ({ metricType: key, data }))
                            .catch(err => {
                                console.error(`Error fetching ${key}:`, err);
                                return { metricType: key, data: [] };
                            })
                    );

                    const metricsResults = await Promise.all(metricsPromises);
                    const metricsMap = metricsResults.reduce((acc, { metricType, data }) => {
                        acc[metricType] = data;
                        return acc;
                    }, {});

                    setMetricsData({ [device.id]: metricsMap });
                } catch (err) {
                    console.error("Metrics fetch error:", err);
                }
            };

            // Initial fetch
            fetchMetricsData();

            // Set up polling interval - 5 seconds for production (changed from 2s)
            intervalId = setInterval(fetchMetricsData, 5000);
        };

        loadData();

        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, []); // Empty dependency array - runs once on mount

    // Add a separate useEffect to handle device/metrics changes
    useEffect(() => {
        if (!selectedDevice?.id || !selectedMetrics) {
            return;
        }

        let intervalId;

        const fetchMetricsData = async () => {
            try {
                const activeMetrics = Object.entries(selectedMetrics)
                    .filter(([_, value]) => value);

                if (activeMetrics.length === 0) {
                    setMetricsData({});
                    return;
                }

                const metricsPromises = activeMetrics.map(([key, metricKey]) =>
                    apiService.fetchDeviceStats(selectedDevice.id, metricKey)
                        .then(data => ({ metricType: key, data }))
                        .catch(err => {
                            console.error(`Error fetching ${key}:`, err);
                            return { metricType: key, data: [] };
                        })
                );

                const metricsResults = await Promise.all(metricsPromises);
                const metricsMap = metricsResults.reduce((acc, { metricType, data }) => {
                    acc[metricType] = data;
                    return acc;
                }, {});

                setMetricsData({ [selectedDevice.id]: metricsMap });
            } catch (err) {
                console.error("Metrics fetch error:", err);
            }
        };

        // Initial fetch
        fetchMetricsData();

        // Set up polling interval - 5 seconds
        intervalId = setInterval(fetchMetricsData, 5000);

        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [selectedDevice, selectedMetrics]); // Re-run when device or metrics change

    useEffect(() => {
        let mounted = true;

        const calculateDimensions = () => {
            if (mounted && containerRef.current) {
                requestAnimationFrame(() => {
                    if (mounted) {
                        updateDimensions();
                    }
                });
            }
        };

        const timers = [
            setTimeout(calculateDimensions, 0),
            setTimeout(calculateDimensions, 50),
            setTimeout(calculateDimensions, 150),
            setTimeout(calculateDimensions, 300)
        ];

        const handleResize = () => calculateDimensions();

        let resizeObserver;
        // istanbul ignore next
        if (window.ResizeObserver && containerRef.current) {
            resizeObserver = new ResizeObserver((entries) => {
                for (let entry of entries) {
                    if (mounted) {
                        const { width, height } = entry.contentRect;
                        setDimensions(prev => {
                            if (prev.width !== width || prev.height !== height) {
                                return { width, height };
                            }
                            return prev;
                        });
                    }
                }
            });
            resizeObserver.observe(containerRef.current);
        }

        window.addEventListener('resize', handleResize);

        return () => {
            mounted = false;
            timers.forEach(timer => clearTimeout(timer));
            window.removeEventListener('resize', handleResize);
            // istanbul ignore next
            if (resizeObserver) {
                resizeObserver.disconnect();
            }
        };
    }, [updateDimensions]);
    // istanbul ignore next
    useEffect(() => {
        if (!selectedDevice || !metricsData[selectedDevice.id]) return;

        if (dimensions.width === 0 || dimensions.height === 0) {
            const timer = setTimeout(updateDimensions, 100);
            return () => clearTimeout(timer);
        }

        const svg = d3.select(svgRef.current);
        svg.selectAll("*").remove();

        const containerWidth = Math.max(dimensions.width, 300);
        const containerHeight = Math.max(dimensions.height, 200);

        const margin = getMarginForTimeFilter(timeFilter, containerWidth);

        const width = Math.max(200, Math.min(containerWidth - margin.left - margin.right - 20, containerWidth * 0.95));
        const height = Math.max(150, Math.min(containerHeight - margin.top - margin.bottom - 20, containerHeight * 0.8));

        const g = svg
            .attr('width', width + margin.left + margin.right)
            .attr('height', height + margin.top + margin.bottom)
            .append('g')
            .attr('transform', `translate(${margin.left},${margin.top})`);

        const deviceMetrics = metricsData[selectedDevice.id];

        const firstMetricData = Object.values(deviceMetrics)[0];
        if (!firstMetricData || firstMetricData.length === 0) return;

        const xScale = d3.scaleBand()
            .domain(firstMetricData.map(d => d.time))
            .range([0, width])
            .padding(0.1);

        // Get the first metric key to determine type
        const firstMetricKey = Object.values(selectedMetrics)?.[0] || '';
        const metricInfo = getMetricInfo(firstMetricKey);

        // Get all values and determine best unit based on metric type
        const allValues = Object.values(deviceMetrics)
            .flatMap(metricData => metricData.map(d => d.value));
        const maxValue = Math.max(...allValues, 0);
        const minValue = Math.min(...allValues, 0);

        let displayUnit, allValuesConverted, yMaxdefault, yMindefault;

        // ---- Temperature (no conversion) ----
        if (metricInfo.type === "temperature") {
            displayUnit = yAxisConfig.unit || metricInfo.baseUnit;
            yMaxdefault = Math.ceil(maxValue * 1.1);
            yMindefault = Math.floor(minValue * 0.9);
        } else if (metricInfo.type === 'bandwidth') {
            // Bandwidth: determine best unit (bps, Kbps, Mbps, Gbps)
            displayUnit = yAxisConfig.unit || getBestBandwidthUnit(maxValue);
            allValuesConverted = allValues.map(v => convertBandwidthToUnit(v, displayUnit, metricInfo.baseUnit));
            const maxConverted = Math.max(...allValuesConverted, 0);
            yMaxdefault = Math.ceil(maxConverted * 1.2);
            yMindefault = 0;
        } else if (metricInfo.type === 'memory') {
            // Memory: determine best unit (Bytes, KB, MB, GB, TB)
            displayUnit = yAxisConfig.unit || getBestMemoryUnit(maxValue);
            allValuesConverted = allValues.map(v => convertToUnit(v, displayUnit));
            const maxConverted = Math.max(...allValuesConverted, 0);
            yMaxdefault = Math.ceil(maxConverted * 1.2);
            yMindefault = 0;
        } else {
            // Generic: no conversion
            displayUnit = yAxisConfig.unit || metricInfo.baseUnit;
            yMaxdefault = Math.ceil(maxValue * 1.2);
            yMindefault = Math.floor(Math.min(0, minValue));
        }

        // Use custom Y-axis config if set, otherwise use defaults
        const yMin = yAxisConfig.min !== null ? yAxisConfig.min : yMindefault;
        const yMax = yAxisConfig.max !== null ? yAxisConfig.max : yMaxdefault;

        const yScale = d3.scaleLinear()
            .domain([yMin, yMax])
            .range([height, 0]);

        const line = d3.line()
            .x(d => xScale(d.time) + xScale.bandwidth() / 2)
            .y(d => {
                if (metricInfo.type === "temperature") return yScale(d.value);
                if (metricInfo.type === "bandwidth") {
                    return yScale(convertBandwidthToUnit(d.value, displayUnit, metricInfo.baseUnit));
                }
                if (metricInfo.type === "memory") {
                    return yScale(convertToUnit(d.value, displayUnit));
                }
                return yScale(d.value);
            })
            .curve(d3.curveCardinal);

        // Grid lines
        g.selectAll('.grid-line')
            .data(yScale.ticks(5))
            .enter()
            .append('line')
            .attr('class', 'grid-line')
            .attr('x1', 0)
            .attr('x2', width)
            .attr('y1', d => yScale(d))
            .attr('y2', d => yScale(d))
            .attr('stroke', '#333')
            .attr('stroke-width', 0.5)
            .attr('opacity', 0.3);

        // X-axis
        const xAxis = g.append('g')
            .attr('transform', `translate(0,${height})`)
            .call(d3.axisBottom(xScale));

        const fontSize = width < 400 ? '10px' : '11px';
        const shouldRotate = timeFilter === '3h' || width < 500;

        xAxis.selectAll('text')
            .attr('fill', '#fff')
            .style('font-size', fontSize)
            .attr('transform', shouldRotate ? 'rotate(-45)' : 'rotate(0)')
            .style('text-anchor', shouldRotate ? 'end' : 'middle')
            .attr('dx', shouldRotate ? '-.8em' : '0')
            .attr('dy', shouldRotate ? '.15em' : '.71em');

        // Y-axis (Clickable)
        const yAxisGroup = g.append("g")
            .call(d3.axisLeft(yScale).ticks(5))
            .style("cursor", "pointer")
            .on("click", () => setShowYAxisModal(true));

        yAxisGroup.selectAll('text')
            .attr('fill', '#fff')
            .style('font-size', fontSize)
            .each(function (d) {
                d3.select(this)
                    .append('title')
                    .text(d.toLocaleString());
            });

        // Add tooltip to Y-axis to indicate it's clickable
        yAxisGroup.append('title')
            .text('Click to configure Y-axis range and unit');

        // Y-axis Label
        g.append("text")
            .attr("transform", "rotate(-90)")
            .attr("x", -height / 2)
            .attr("y", -margin.left + 7.5)
            .attr("text-anchor", "middle")
            .attr("fill", "#fff")
            .style("font-size", fontSize)
            .text(displayUnit);

        g.selectAll(".domain").attr("stroke", "#555");
        g.selectAll(".tick line").attr("stroke", "#555");

        const timeLabelY = shouldRotate ? height + (margin.bottom - 10) : height + 40;

        g.append('text')
            .attr('x', width)
            .attr('y', timeLabelY)
            .attr('text-anchor', 'end')
            .attr('fill', '#fff')
            .style('font-size', fontSize)
            .text('Time');

        // Create tooltip (add this ONCE before the forEach loop)
        const tooltip = d3.select('body')
            .selectAll('.line-graph-tooltip')
            .data([null])
            .join('div')
            .attr('class', 'line-graph-tooltip')
            .style('position', 'absolute')
            .style('background', 'rgba(0, 0, 0, 0.9)')
            .style('color', 'white')
            .style('padding', '8px 12px')
            .style('border-radius', '6px')
            .style('font-size', '13px')
            .style('pointer-events', 'none')
            .style('opacity', 0)
            .style('z-index', 1000)
            .style('box-shadow', '0 2px 8px rgba(0,0,0,0.3)');

        // Draw lines and dots for each metric
        Object.entries(deviceMetrics).forEach(([metricType, data]) => {
            if (!data || data.length === 0) return;

            // Draw line
            g.append('path')
                .datum(data)
                .attr('fill', 'none')
                .attr('stroke', metricColors[metricType] || '#0d6efd')
                .attr('stroke-width', width < 400 ? 2 : 3)
                .attr('stroke-opacity', 0.8)
                .attr('d', line);

            // Draw dots with tooltip - Using appropriate conversion based on metric type
            g.selectAll(`.dots-${metricType.replace(/\s/g, '-')}`)
                .data(data)
                .enter()
                .append("circle")
                .attr("class", `dots-${metricType.replace(/\s/g, "-")}`)
                .attr("cx", d => xScale(d.time) + xScale.bandwidth() / 2)
                .attr("cy", d => {
                    if (metricInfo.type === "temperature") return yScale(d.value);
                    if (metricInfo.type === "bandwidth") {
                        return yScale(convertBandwidthToUnit(d.value, displayUnit, metricInfo.baseUnit));
                    }
                    if (metricInfo.type === "memory") {
                        return yScale(convertToUnit(d.value, displayUnit));
                    }
                    return yScale(d.value);
                })
                .attr("r", width < 400 ? 3 : 4)
                .attr("fill", metricColors[metricType] || "#0d6efd")
                .attr("stroke", "#1a1a1a")
                .attr("stroke-width", 1)
                .style("cursor", "pointer")

                // ---- Tooltip Fix (matches Y-axis unit exactly!) ----
                .on("mouseenter", function (event, d) {
                    d3.select(this)
                        .transition()
                        .duration(200)
                        .attr("r", width < 400 ? 6 : 8);

                    const convertedValue =
                        metricInfo.type === "temperature"
                            ? d.value
                            : metricInfo.type === "bandwidth"
                                ? convertBandwidthToUnit(d.value, displayUnit, metricInfo.baseUnit)
                                : metricInfo.type === "memory"
                                    ? convertToUnit(d.value, displayUnit)
                                    : d.value;

                    const formattedValue = `${convertedValue.toFixed(2)} ${displayUnit}`;

                    tooltip
                        .style("opacity", 1)
                        .html(`
                        <div style="margin-bottom: 2px;">Time: ${d.time}</div>
                        <div><strong style="font-size: 15px;">${formattedValue}</strong></div>
                    `)
                        .style("left", event.pageX + 15 + "px")
                        .style("top", event.pageY - 10 + "px");
                })
                .on("mousemove", function (event) {
                    tooltip
                        .style("left", event.pageX + 15 + "px")
                        .style("top", event.pageY - 10 + "px");
                })
                .on("mouseleave", function () {
                    d3.select(this)
                        .transition()
                        .duration(200)
                        .attr("r", width < 400 ? 3 : 4);

                    tooltip.style("opacity", 0);
                });
        });

        // Legend
        const legendWidth = Math.min(150, width * 0.3);
        const legend = g.append('g')
            .attr('class', 'legend')
            .attr('transform', `translate(${width - legendWidth}, 20)`);

        let legendY = 0;
        Object.keys(deviceMetrics).forEach(metricType => {
            const legendItem = legend.append('g')
                .attr('transform', `translate(0, ${legendY})`);

            legendItem.append('line')
                .attr('x1', 0)
                .attr('x2', 15)
                .attr('y1', 0)
                .attr('y2', 0)
                .attr('stroke', metricColors[metricType] || '#0d6efd')
                .attr('stroke-width', 3);

            legendItem.append('text')
                .attr('x', 20)
                .attr('y', 0)
                .attr('dy', '0.35em')
                .attr('fill', '#fff')
                .style('font-size', fontSize)
                .text(`Device ID: ${selectedDevice.name}`);

            legendY += 18;
        });

    }, [selectedDevice, metricsData, dimensions, updateDimensions, timeFilter, yAxisConfig, selectedMetrics, getMetricInfo]);

    const toggleExpanded = useCallback((item, level = 0) => {
        setExpandedItems(prev => {
            const newExpanded = { ...prev };
            const isCurrentlyExpanded = newExpanded[item];
            newExpanded[item] = !isCurrentlyExpanded;

            if (!isCurrentlyExpanded) {
                if (level === 1) {
                    clustersData.forEach(cluster => {
                        if (cluster.name !== item) {
                            newExpanded[cluster.name] = false;
                            cluster.nodes.forEach(node => {
                                newExpanded[node.name] = false;
                            });
                        }
                    });
                } else if (level === 2) {
                    const parentCluster = clustersData.find(cluster =>
                        cluster.nodes.some(node => node.name === item)
                    );
                    if (parentCluster) {
                        parentCluster.nodes.forEach(node => {
                            if (node.name !== item) {
                                newExpanded[node.name] = false;
                            }
                        });
                    }
                }
            } else {
                if (level === 1) {
                    const cluster = clustersData.find(c => c.name === item);
                    if (cluster) {
                        cluster.nodes.forEach(node => {
                            newExpanded[node.name] = false;
                        });
                    }
                }
            }

            return newExpanded;
        });
    }, [clustersData]);
    // istanbul ignore next
    const selectDevice = async (device) => {
        setSelectedDevice(device);

        if (!metricsData[device.id]) {
            try {
                const metricsPromises = Object.entries(selectedMetrics || {})
                    .filter(([_, value]) => value)
                    .map(([key, metricKey]) =>
                        apiService.fetchDeviceStats(device.id, metricKey)
                            .then(data => ({ metricType: key, data }))
                    );

                const metricsResults = await Promise.all(metricsPromises);
                const metricsMap = metricsResults.reduce((acc, { metricType, data }) => {
                    acc[metricType] = data;
                    return acc;
                }, {});

                setMetricsData(prev => ({
                    ...prev,
                    [device.id]: metricsMap
                }));
            } catch (err) {
                setError('Failed to load metrics. Please try again.');
                console.error('Fetch metrics error:', err);
            }
        }
    };
    // istanbul ignore next
    const handleYAxisSave = (config) => {
        setYAxisConfig(config);
    };

    // Get metric info for modal
    // istanbul ignore next
    const firstMetricKey = Object.values(selectedMetrics)?.[0] || '';
    const currentMetricInfo = getMetricInfo(firstMetricKey);

    return (
        <div className="device-card-container">
            <div className="device-card-wrapper">
                {error && <ErrorBanner message={error} />}
                <div className="device-card-content">
                    <Sidebar
                        loading={loading}
                        expandedItems={expandedItems}
                        clustersData={clustersData}
                        selectedDevice={selectedDevice}
                        selectedMetrics={selectedMetrics}
                        onToggleExpanded={toggleExpanded}
                        onSelectDevice={selectDevice}
                    />
                    <ChartArea
                        selectedDevice={selectedDevice}
                        dimensions={dimensions}
                        containerRef={containerRef}
                        svgRef={svgRef}
                    />
                </div>
            </div>

            <YAxisConfigModal
                isOpen={showYAxisModal}
                onClose={() => setShowYAxisModal(false)}
                onSave={handleYAxisSave}
                currentMin={yAxisConfig.min}
                currentMax={yAxisConfig.max}
                currentUnit={yAxisConfig.unit}
                availableUnits={currentMetricInfo.units}
                defaultUnit={currentMetricInfo.baseUnit}
            />
        </div>
    );
};

const ErrorBanner = ({ message }) => (
    <div className="error-banner">
        {message}
    </div>
);

ErrorBanner.propTypes = {
    message: PropTypes.string.isRequired
};

const Sidebar = ({
    loading,
    expandedItems,
    clustersData,
    selectedDevice,
    selectedMetrics,
    onToggleExpanded,
    onSelectDevice
}) => (
    <div className="sidebar-device">
        {loading ? (
            <div className="loading-text">Loading...</div>
        ) : (
            <>
                <div className="sidebar-section">
                    <TreeItem
                        label="Clusters"
                        hasChildren={true}
                        isExpanded={expandedItems["Clusters"]}
                        toggleExpanded={(label) => onToggleExpanded(label, 0)}
                    >
                        {clustersData.map(cluster => (
                            <TreeItem
                                key={cluster.id}
                                label={cluster.name}
                                level={1}
                                hasChildren={true}
                                isExpanded={expandedItems[cluster.name]}
                                toggleExpanded={(label) => onToggleExpanded(label, 1)}
                            >
                                {cluster.nodes.map(node => (
                                    <TreeItem
                                        key={node.id}
                                        label={node.name}
                                        level={2}
                                        hasChildren={node.devices.length > 0}
                                        isExpanded={expandedItems[node.name]}
                                        toggleExpanded={(label) => onToggleExpanded(label, 2)}
                                    >
                                        {node.devices.map(device => (
                                            <TreeItem
                                                key={device.id}
                                                label={`...${String(device.id).slice(-5)}`}
                                                level={3}
                                                onClick={() => onSelectDevice(device)}
                                                isSelected={selectedDevice?.id === device.id}
                                                isExpanded={false}
                                                toggleExpanded={(label) => onToggleExpanded(label, 3)}
                                            />
                                        ))}
                                    </TreeItem>
                                ))}
                            </TreeItem>
                        ))}
                    </TreeItem>
                </div>

                <div className="metrics-section">
                    {Object.keys(selectedMetrics || {}).map(metric => (
                        <MetricItem key={metric} label={metric} />
                    ))}
                </div>
            </>
        )}
    </div>
);
Sidebar.propTypes = {
    loading: PropTypes.bool.isRequired,
    expandedItems: PropTypes.object.isRequired,
    clustersData: PropTypes.arrayOf(
        PropTypes.shape({
            id: PropTypes.string.isRequired,
            name: PropTypes.string.isRequired,
            nodes: PropTypes.arrayOf(
                PropTypes.shape({
                    id: PropTypes.string.isRequired,
                    name: PropTypes.string.isRequired,
                    devices: PropTypes.arrayOf(
                        PropTypes.shape({
                            id: PropTypes.string.isRequired,
                            name: PropTypes.string.isRequired
                        })
                    ).isRequired
                })
            ).isRequired
        })
    ).isRequired,
    selectedDevice: PropTypes.shape({
        id: PropTypes.string.isRequired,
        name: PropTypes.string.isRequired
    }),
    selectedMetrics: PropTypes.objectOf(PropTypes.string),
    onToggleExpanded: PropTypes.func.isRequired,
    onSelectDevice: PropTypes.func.isRequired
};
const ChartArea = ({ selectedDevice, dimensions, containerRef, svgRef }) => (
    <div className="chart-area">
        {selectedDevice ? (
            <div className="chart-container">
                <div ref={containerRef} className="chart-inner-container">
                    <svg
                        ref={svgRef}
                        className="chart-svg"
                    />
                    {(dimensions.width === 0 || dimensions.height === 0) && (
                        <div className="chart-loading">
                            <div>Loading chart...</div>
                        </div>
                    )}
                </div>
            </div>
        ) : (
            <div className="chart-placeholder">
                Select a device to view metrics
            </div>
        )}
    </div>
);
ChartArea.propTypes = {
    selectedDevice: PropTypes.shape({
        id: PropTypes.string.isRequired,
        name: PropTypes.string.isRequired
    }),
    dimensions: PropTypes.shape({
        width: PropTypes.number.isRequired,
        height: PropTypes.number.isRequired
    }).isRequired,
    containerRef: PropTypes.object.isRequired,
    svgRef: PropTypes.object.isRequired
};
DeviceCard.propTypes = {
    selectedMetrics: PropTypes.objectOf(PropTypes.string),
    setSelectedMetrics: PropTypes.func
};

export default DeviceCard;