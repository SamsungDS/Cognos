import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import './deviceCard.css';
import MetricItem from './MetricItem';
import TreeItem from './TreeItem';
import { metricColors, TIME_FILTERS, apiService, getMarginForTimeFilter } from '../../utils/deviceStats-utils';

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

    // Get container dimensions
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

    // Force dimension update when selected device changes
    useEffect(() => {
        if (selectedDevice) {
            const timer = setTimeout(() => {
                updateDimensions();
            }, 100);
            return () => clearTimeout(timer);
        }
    }, [selectedDevice, updateDimensions]);

    // Load clusters data on component mount
    useEffect(() => {
        const loadData = async () => {
            setLoading(true);
            setError(null);

            try {
                const clusters = await apiService.fetchClusters();
                setClustersData(clusters);

                const initialExpanded = { 'Clusters': true };

                // Safely navigate the hierarchy
                if (clusters && clusters.length > 0) {
                    const firstCluster = clusters[0];
                    initialExpanded[firstCluster.name] = true;

                    if (firstCluster.nodes && firstCluster.nodes.length > 0) {
                        const firstNode = firstCluster.nodes[0];
                        initialExpanded[firstNode.name] = true;

                        if (firstNode.devices && firstNode.devices.length > 0) {
                            const firstDevice = firstNode.devices[0];
                            setSelectedDevice(firstDevice);

                            const metrics = await apiService.fetchMetrics(firstDevice.id, timeFilter);
                            setMetricsData({ [firstDevice.id]: metrics });
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

        loadData();
    }, []);

    // Handle resize events and initial dimension calculation
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

        const handleResize = () => {
            calculateDimensions();
        };

        let resizeObserver;
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
            if (resizeObserver) {
                resizeObserver.disconnect();
            }
        };
    }, [updateDimensions]);

    // Generate chart when dependencies change
    useEffect(() => {
        if (!selectedDevice || !metricsData[selectedDevice.id]) return;

        if (dimensions.width === 0 || dimensions.height === 0) {
            const timer = setTimeout(() => {
                updateDimensions();
            }, 100);
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

        const deviceData = metricsData[selectedDevice.id];

        // Scales
        const xScale = d3.scaleBand()
            .domain(deviceData.capacity.map(d => d.time))
            .range([0, width])
            .padding(0.1);

        const yScale = d3.scaleLinear()
            .domain([0, 100])
            .range([height, 0]);

        // Line generator
        const line = d3.line()
            .x(d => xScale(d.time) + xScale.bandwidth() / 2)
            .y(d => yScale(d.value))
            .curve(d3.curveCardinal);

        // Add grid lines
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

        // X Axis with responsive text handling
        const xAxis = g.append('g')
            .attr('transform', `translate(0,${height})`)
            .call(d3.axisBottom(xScale));

        const fontSize = width < 400 ? '10px' : '11px';
        const shouldRotate = timeFilter === '3h' || width < 500;

        xAxis.selectAll('text')
            .attr('fill', '#888')
            .style('font-size', fontSize)
            .attr('transform', shouldRotate ? 'rotate(-45)' : 'rotate(0)')
            .style('text-anchor', shouldRotate ? 'end' : 'middle')
            .attr('dx', shouldRotate ? '-.8em' : '0')
            .attr('dy', shouldRotate ? '.15em' : '.71em');

        // Y Axis
        g.append('g')
            .call(d3.axisLeft(yScale))
            .selectAll('text')
            .attr('fill', '#888')
            .style('font-size', fontSize);

        g.selectAll('.domain').attr('stroke', '#555');
        g.selectAll('.tick line').attr('stroke', '#555');

        // Add "Time" label
        const timeLabelY = shouldRotate ? height + (margin.bottom - 10) : height + 40;

        g.append('text')
            .attr('x', width)
            .attr('y', timeLabelY)
            .attr('text-anchor', 'end')
            .attr('fill', '#888')
            .style('font-size', fontSize)
            .text('Time');

        // Add lines for selected metrics
        const metricsToRender = [
            { key: 'CXL Capacity', data: deviceData.capacity },
            { key: 'CXL Usage', data: deviceData.usage },
            { key: 'CXL Bandwidth', data: deviceData.bandwidth }
        ];

        metricsToRender.forEach(metric => {
            if (selectedMetrics && selectedMetrics[metric.key]) {
                g.append('path')
                    .datum(metric.data)
                    .attr('fill', 'none')
                    .attr('stroke', metricColors[metric.key])
                    .attr('stroke-width', width < 400 ? 2 : 3)
                    .attr('stroke-opacity', 0.8)
                    .attr('d', line);

                // Add dots
                g.selectAll(`.dots-${metric.key.replace(/\s/g, '-')}`)
                    .data(metric.data)
                    .enter()
                    .append('circle')
                    .attr('class', `dots-${metric.key.replace(/\s/g, '-')}`)
                    .attr('cx', d => xScale(d.time) + xScale.bandwidth() / 2)
                    .attr('cy', d => yScale(d.value))
                    .attr('r', width < 400 ? 3 : 4)
                    .attr('fill', metricColors[metric.key])
                    .attr('stroke', '#1a1a1a')
                    .attr('stroke-width', 1);
            }
        });

        // Add responsive legend
        const legendWidth = Math.min(150, width * 0.3);
        const legend = g.append('g')
            .attr('class', 'legend')
            .attr('transform', `translate(${width - legendWidth}, 20)`);

        let legendY = 0;
        Object.entries(selectedMetrics || {}).forEach(([metric, isSelected]) => {
            if (isSelected) {
                const legendItem = legend.append('g')
                    .attr('transform', `translate(0, ${legendY})`);

                legendItem.append('line')
                    .attr('x1', 0)
                    .attr('x2', 15)
                    .attr('y1', 0)
                    .attr('y2', 0)
                    .attr('stroke', metricColors[metric])
                    .attr('stroke-width', 3);

                legendItem.append('text')
                    .attr('x', 20)
                    .attr('y', 0)
                    .attr('dy', '0.35em')
                    .attr('fill', '#ccc')
                    .style('font-size', fontSize)
                    .text(metric);

                legendY += 18;
            }
        });

    }, [selectedDevice, selectedMetrics, metricsData, timeFilter, dimensions, updateDimensions]);

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

    const selectDevice = async (device) => {
        setSelectedDevice(device);

        if (!metricsData[device.id]) {
            try {
                const newMetricsData = await apiService.fetchMetrics(device.id, timeFilter);
                setMetricsData(prev => ({
                    ...prev,
                    [device.id]: newMetricsData
                }));
            } catch (err) {
                setError('Failed to load metrics. Please try again.');
                console.error('Fetch metrics error:', err);
            }
        }
    };

    const handleTimeFilterChange = async (filter) => {
        setTimeFilter(filter);
        if (selectedDevice) {
            try {
                const newMetricsData = await apiService.fetchMetrics(selectedDevice.id, filter);
                setMetricsData(prev => ({
                    ...prev,
                    [selectedDevice.id]: newMetricsData
                }));
            } catch (err) {
                setError('Failed to load metrics. Please try again.');
                console.error('Fetch metrics error:', err);
            }
        }
    };

    return (
        <div style={{ height: '100%', backgroundColor: '#1a1a1a', padding: '20px' }}>
            <div style={{
                backgroundColor: '#212529',
                border: '1px solid #444',
                borderRadius: '10px',
                height: '100%',
                overflow: 'hidden'
            }}>
                {error && (
                    <div style={{
                        backgroundColor: '#dc3545',
                        color: 'white',
                        padding: '10px',
                        textAlign: 'center',
                        fontSize: '14px'
                    }}>
                        {error}
                    </div>
                )}

                <div style={{ display: 'flex', height: '100%' }}>
                    {/* Sidebar */}
                    <div style={{
                        width: '25%',
                        minWidth: '200px',
                        borderRight: '1px solid #444',
                        padding: '15px',
                        overflowY: 'auto',
                        backgroundColor: '#1a1a1a'
                    }}>
                        {loading ? (
                            <div style={{ color: '#888' }}>Loading...</div>
                        ) : (
                            <>
                                {/* Clusters Section */}
                                <div style={{ marginBottom: '20px' }}>
                                    <TreeItem
                                        label="Clusters"
                                        hasChildren={true}
                                        isExpanded={expandedItems["Clusters"]}
                                        toggleExpanded={(label) => toggleExpanded(label, 0)}
                                    >
                                        {clustersData.map(cluster => (
                                            <TreeItem
                                                key={cluster.id}
                                                label={cluster.name}
                                                level={1}
                                                hasChildren={true}
                                                isExpanded={expandedItems[cluster.name]}
                                                toggleExpanded={(label) => toggleExpanded(label, 1)}
                                            >
                                                {cluster.nodes.map(node => (
                                                    <TreeItem
                                                        key={node.id}
                                                        label={node.name}
                                                        level={2}
                                                        hasChildren={node.devices.length > 0}
                                                        isExpanded={expandedItems[node.name]}
                                                        toggleExpanded={(label) => toggleExpanded(label, 2)}
                                                    >
                                                        {node.devices.map(device => (
                                                            <TreeItem
                                                                key={device.id}
                                                                label={device.name}
                                                                level={3}
                                                                onClick={() => selectDevice(device)}
                                                                isSelected={selectedDevice?.id === device.id}
                                                                isExpanded={false}
                                                                toggleExpanded={(label) => toggleExpanded(label, 3)}
                                                            />
                                                        ))}
                                                    </TreeItem>
                                                ))}
                                            </TreeItem>
                                        ))}
                                    </TreeItem>
                                </div>

                                {/* Metrics Section */}
                                <div>
                                    <div style={{ marginTop: '10px' }}>
                                        {Object.keys(selectedMetrics || {}).map(metric => (
                                            <MetricItem key={metric} label={metric} />
                                        ))}
                                    </div>
                                </div>
                            </>
                        )}
                    </div>

                    {/* Chart Area */}
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '15px' }}>
                        {/* Time Filter Controls */}
                        <div style={{ marginBottom: '15px' }}>
                            <div style={{ display: 'flex', gap: '10px' }}>
                                {TIME_FILTERS.map(filter => (
                                    <button
                                        key={filter.key}
                                        onClick={() => handleTimeFilterChange(filter.key)}
                                        style={{
                                            flex: 1,
                                            padding: '8px 16px',
                                            fontSize: '14px',
                                            backgroundColor: timeFilter === filter.key ? '#0d6efd' : '#2a2a2a',
                                            color: 'white',
                                            border: timeFilter === filter.key ? '1px solid #0d6efd' : '1px solid #555',
                                            borderRadius: '4px',
                                            cursor: 'pointer',
                                            transition: 'all 0.2s'
                                        }}
                                        onMouseEnter={(e) => {
                                            if (timeFilter !== filter.key) {
                                                e.currentTarget.style.backgroundColor = '#3a3a3a';
                                            }
                                        }}
                                        onMouseLeave={(e) => {
                                            if (timeFilter !== filter.key) {
                                                e.currentTarget.style.backgroundColor = '#2a2a2a';
                                            }
                                        }}
                                    >
                                        {filter.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {selectedDevice ? (
                            <div style={{ flex: 1, position: 'relative', minHeight: '200px' }}>
                                <div
                                    ref={containerRef}
                                    style={{
                                        position: 'absolute',
                                        top: 0,
                                        left: 0,
                                        right: 0,
                                        bottom: 0,
                                        minHeight: '200px',
                                        minWidth: '300px'
                                    }}
                                >
                                    <svg
                                        ref={svgRef}
                                        style={{
                                            width: '100%',
                                            height: '100%',
                                            maxWidth: '100%',
                                            maxHeight: '100%',
                                            minHeight: '200px',
                                            display: 'block'
                                        }}
                                    />
                                    {(dimensions.width === 0 || dimensions.height === 0) && (
                                        <div style={{
                                            position: 'absolute',
                                            top: '50%',
                                            left: '50%',
                                            transform: 'translate(-50%, -50%)',
                                            color: '#888',
                                            textAlign: 'center'
                                        }}>
                                            <div style={{ marginBottom: '10px' }}>Loading chart...</div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ) : (
                            <div style={{
                                flex: 1,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: '#888',
                                fontSize: '16px'
                            }}>
                                Select a device to view metrics
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default DeviceCard;