import { Row, Col, Spinner } from "react-bootstrap";
import Chart from "react-google-charts";
import ProgressBar from "react-bootstrap/ProgressBar";
import PropTypes from "prop-types";
import "../pages/metrics.css";
import "../pages/dashboard.css";

export const HostList = ["Host 1", "Host 2", "Host 3", "Host 4", "Host 5", "Host 6", "Host 7", "Host 8"];
export const clusters = ["Cluster-A", "Cluster-B"];
export const VIEW_MODES = {
    CMMB: "CMM-B",
    HOST: "host"
};

// ============================================================================
// CHART OPTIONS
// ============================================================================
const getMemCapacityOptions = () => ({
    colors: ["#FFB546", "#0077C8", "#FE8E73", "#FEAE00", "B37328"],
    pieSliceText: 'value',
    backgroundColor: { fill: 'transparent' },
    animation: { startup: true },
    is3D: true,
    label: 'GB',
    annotations: {
        textStyle: {
            fontName: 'Times-Roman',
            fontSize: 36,
            bold: true,
            italic: true,
            color: 'black',
            auraColor: '#FFFFFD',
            opacity: 0.8
        }
    },
    pieSliceTextStyle: {
        color: 'black',
        fontSize: 16,
        bold: true
    },
    legend: { textStyle: { color: '#FFFFFD', fontSize: 16 } },
    chartArea: { width: "95%", height: "95%", top: 50, bottom: 40 },
});

const getCmmbMemoryDataOptions = () => ({
    isStacked: true,
    height: 180,
    titleTextStyle: { color: "#FFFFFD", fontSize: 25, bold: true },
    colors: ["#FFB546", "#0077C8"],
    hAxis: {
        title: "Time",
        textStyle: { color: "#FFFFFD" },
        titleTextStyle: { color: "#FFFFFD" },
        gridlines: { color: "#4C4C3B" },
    },
    vAxis: {
        minValue: 0,
        title: "Usage (MB)",
        textStyle: { color: "#FFFFFD" },
        titleTextStyle: { color: "#FFFFFD" },
    },
    curveType: "function",
    lineWidth: 2,
    areaOpacity: 0.7,
    chartArea: { width: "70%", height: "100%", top: 50, bottom: 50 },
    backgroundColor: { fill: "transparent" },
    animation: { startup: true },
    annotations: {
        textStyle: {
            fontName: "Times-Roman",
            fontSize: 18,
            bold: true,
            italic: true,
            color: "#FFFFFD",
            auraColor: "#FFFFFD",
            opacity: 0.8,
        },
    },
    legend: {
        position: "bottom",
        textStyle: { color: "#FFFFFD" }
    },
});

export const LoadingSpinner = ({ height = 150 }) => (
    <div className="spinner-style" style={{ height }}>
        <Spinner animation="border" variant="secondary" />
    </div>
);

LoadingSpinner.propTypes = {
    height: PropTypes.number
};

export const DeviceCountCard = ({ hostsCount, devicesCount, isLoading }) => {
    if (isLoading) {
        return (
            <div className="device_card info-memo-com" id="mem-info">
                <LoadingSpinner />
            </div>
        );
    }

    return (
        <div
            className="device_card info-memo-com"
            id="mem-info"
            style={{ fontFamily: "Samsung One", verticalAlign: "top" }}
        >
            <Row className="row-info-memo">
                <Col>
                    <div style={{ color: "white", display: "inline", fontWeight: "bold" }}>
                        Total Hosts &nbsp;
                    </div>
                </Col>
                <Col>
                    <span className="arrow">
                        <i className="right"></i>
                    </span>
                </Col>
                <Col>
                    <span className="circle" style={{ color: "#00B3E3" }}>
                        {hostsCount || 0}
                    </span>
                </Col>
            </Row>
            <Row className="row-info-memo">
                <Col>
                    <div style={{ color: "white", display: "inline", fontWeight: "bold" }}>
                        Devices
                    </div>
                </Col>
                <Col>
                    <span className="arrow">
                        <i className="right"></i>
                    </span>
                </Col>
                <Col>
                    <div className="circle" style={{ color: "#00B3E3" }}>
                        {devicesCount || 0}
                    </div>
                </Col>
            </Row>
        </div>
    );
};

DeviceCountCard.propTypes = {
    hostsCount: PropTypes.number,
    devicesCount: PropTypes.number,
    isLoading: PropTypes.bool.isRequired
};

export const CapacityCard = ({ viewMode, capacityData, memCapacityData, isLoading }) => {
    const isCMMB = viewMode === VIEW_MODES.CMMB;
    const title = isCMMB ? "Expansion Chessis" : "Aggregated Cluster Memory";

    // Helper function to convert GB to TB with proper formatting
    const convertGBtoTB = (gbValue) => {
        if (!gbValue || gbValue === 0) return { value: 0, unit: 'GB' };
        const numericValue = typeof gbValue === 'string' ? parseFloat(gbValue.replace(/,/g, '')) : gbValue;

        // Convert to TB if value is 1000 GB or more
        if (numericValue >= 1000) {
            return {
                value: (numericValue / 1024).toFixed(2),
                unit: 'TB'
            };
        }
        return {
            value: numericValue.toFixed(2),
            unit: 'GB'
        };
    };

    // Format display value with unit
    const formatCapacity = (gbValue) => {
        const converted = convertGBtoTB(gbValue);
        return `${converted.value} ${converted.unit}`;
    };

    // Calculate memory per core multiplier
    const calculateMemoryPerCore = () => {
        if (!memCapacityData || memCapacityData.length <= 1) return null;

        let dramCapacity = 0;
        let cxlCapacity = 0;

        memCapacityData.slice(1).forEach(item => {
            const label = item[0].toLowerCase();
            const value = item[1];

            if (label.includes('dram')) {
                dramCapacity = value;
            } else if (label.includes('cxl')) {
                cxlCapacity = value;
            }
        });

        if (dramCapacity > 0) {
            const totalCapacity = cxlCapacity + dramCapacity;
            const multiplier = totalCapacity / dramCapacity;
            return multiplier.toFixed(1);
        }

        return null;
    };

    // Calculate total capacity
    const calculateTotalCapacity = () => {
        if (!memCapacityData || memCapacityData.length <= 1) return 0;

        let total = 0;
        memCapacityData.slice(1).forEach(item => {
            total += item[1];
        });

        return total;
    };

    // Transform memCapacityData to add GB suffix for tooltip display
    const getTransformedMemCapacityData = () => {
        if (!memCapacityData || memCapacityData.length <= 1) return memCapacityData;

        // Create a copy and add formatted strings for tooltips
        const transformedData = memCapacityData.map((row, index) => {
            if (index === 0) {
                // Header row - add a column for formatted values
                return [...row, { role: 'tooltip', type: 'string' }];
            } else {
                // Data rows - add formatted tooltip value with GB suffix
                const label = row[0];
                const value = row[1];
                const tooltip = `${label}: ${value} GB`;
                return [...row, tooltip];
            }
        });

        return transformedData;
    };

    // Updated chart options with GB values in tooltip - merges with base options
    const getUpdatedMemCapacityOptions = () => {
        const baseOptions = getMemCapacityOptions();

        return {
            ...baseOptions,
            tooltip: {
                trigger: 'item',
                isHtml: false,
                textStyle: {
                    color: '#000000',
                    fontSize: 14
                }
            },
            legend: {
                position: 'none' // Hide legend since we removed the custom legend
            },
            pieSliceText: 'percentage', // Show percentages in slices
            pieSliceTextStyle: {
                color: 'black',
                fontSize: 12,
                bold: true
            },
            chartArea: {
                width: '95%',
                height: '95%'
            },
            pieStartAngle: 0 // Ensures slices start at top for better percentage visibility
        };
    };

    if (isLoading) {
        return (
            <div className="device_card system-memory-allocated" id="sys-mem-allocated-id">
                <div style={{ color: "white", fontWeight: "bold", fontFamily: "Samsung" }}>
                    <h4 className="cmmb-memory-heading">
                        {title} <span style={{ color: "white" }}>Capacity</span>
                    </h4>
                </div>
                <LoadingSpinner />
            </div>
        );
    }

    // Convert capacity values for display
    const usedCapacityDisplay = formatCapacity(capacityData.used_capacity || 0);
    const totalCapacityDisplay = formatCapacity(capacityData.total_capacity || 0);
    const memoryPerCore = calculateMemoryPerCore();
    const totalMemoryCapacity = calculateTotalCapacity();

    return (
        <div className="device_card system-memory-allocated" id="sys-mem-allocated-id">
            <div style={{ color: "white", fontWeight: "bold", fontFamily: "Samsung" }}>
                <h4 className="cmmb-memory-heading">
                    {title} <span style={{ color: "white" }}>Capacity</span>
                </h4>
            </div>
            <div>
                {isCMMB ? (
                    <>
                        <ProgressBar
                            style={{ height: 24, fontWeight: "bold" }}
                            now={capacityData.used_capacity_percentage}
                            key={1}
                            className="host1"
                        />
                        <div style={{
                            color: "white",
                            textAlign: "center",
                            marginTop: "10px"
                        }}>
                            {`Used Memory ${usedCapacityDisplay}`}
                        </div>
                        <div style={{
                            color: "white",
                            textAlign: "center",
                            marginTop: "5px"
                        }}>
                            {`Total: ${totalCapacityDisplay}`}
                        </div>
                    </>
                ) : (
                        <div className="capacity-grid-container">
                            {/* Left Half - Memory per core display */}
                            <div className="memory-per-core-container">
                                {memoryPerCore && (
                                    <div className="memory-per-core-content">
                                        <div className="memory-multiplier">
                                            {memoryPerCore}
                                        </div>
                                        <div className="memory-multiplier-label">
                                            more memory<br />per core
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Right Half - Pie Chart with Total */}
                            <div className="pie-chart-container">
                                <div className="pie-chart-wrapper">
                                    <Chart
                                        chartType="PieChart"
                                        data={getTransformedMemCapacityData()}
                                        options={getUpdatedMemCapacityOptions()}
                                        width="100%"
                                        height="130px"
                                    />
                                </div>
                                <div className="pie-chart-total">
                                        Total: {totalMemoryCapacity} GB
                                </div>
                            </div>
                        </div>
                )}
            </div>
        </div>
    );
};

CapacityCard.propTypes = {
    viewMode: PropTypes.oneOf([VIEW_MODES.CMMB, VIEW_MODES.HOST]).isRequired,
    capacityData: PropTypes.shape({
        used_capacity: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
        total_capacity: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
        used_capacity_percentage: PropTypes.number
    }).isRequired,
    memCapacityData: PropTypes.arrayOf(
        PropTypes.arrayOf(
            PropTypes.oneOfType([PropTypes.string, PropTypes.number])
        )
    ),
    isLoading: PropTypes.bool.isRequired
};

export const BandwidthCard = ({ viewMode, bandwidthData, isLoading }) => {
    const isCMMB = viewMode === VIEW_MODES.CMMB;
    const title = isCMMB ? "Expansion Chessis" : "Aggregated Cluster CXL";

    if (isLoading) {
        return (
            <div className="device_card system-memory-allocated" id="sys-mem-allocated-id">
                <div className="text-white fw-bold" style={{ fontFamily: "Samsung" }}>
                    <h4 className="cmmb-memory-heading mb-0">
                        {title} <span className="text-white">Bandwidth</span>
                    </h4>
                </div>
                <LoadingSpinner />
            </div>
        );
    }

    const maxBandwidth = bandwidthData.max_bandwidth || 0;
    const usedBandwidth = bandwidthData.used_bandwidth || 0;
    const usedPercentage = bandwidthData.used_percentage_bandwidth || 0;

    return (
        <div className="device_card system-memory-allocated" id="sys-mem-allocated-id">
            {/* Header */}
            <div className="text-white fw-bold mb-3" style={{ fontFamily: "Samsung" }}>
                <h4 className="cmmb-memory-heading mb-0">
                    {title} <span className="text-white">Bandwidth</span>
                </h4>
            </div>

            {/* Progress Bar Section */}
            <div className="pt-3">
                {/* Progress Bar */}
                <ProgressBar
                    now={usedPercentage}
                    className="host1 mb-2"
                    style={{ height: 24, fontWeight: "bold" }}
                />

                {/* Labels Container */}
                <div className="d-flex justify-content-between align-items-center text-white">
                    {/* Left Label - 0 */}
                    <div className="flex-shrink-0">
                        <small>0 GBps</small>
                    </div>

                    {/* Center Label - Used Bandwidth */}
                    <div className="text-center flex-grow-1 px-2">
                        <span className="d-none d-md-inline">Used Bandwidth </span>
                        <span className="fw-bold">{usedBandwidth} GBps</span>
                    </div>

                    {/* Right Label - Max Bandwidth */}
                    <div className="flex-shrink-0">
                        <small>{maxBandwidth} GBps</small>
                    </div>
                </div>
            </div>
        </div>
    );
};

BandwidthCard.propTypes = {
    viewMode: PropTypes.oneOf([VIEW_MODES.CMMB, VIEW_MODES.HOST]).isRequired,
    bandwidthData: PropTypes.shape({
        max_bandwidth: PropTypes.number,
        used_bandwidth: PropTypes.number,
        used_percentage_bandwidth: PropTypes.number
    }).isRequired,
    isLoading: PropTypes.bool.isRequired
};

export const MemoryUsageChart = ({ viewMode, memoryData, isLoading }) => {
    const isCMMB = viewMode === VIEW_MODES.CMMB;
    const title = isCMMB ? "Expansion Chessis" : "Cluster Memory";

    if (isLoading) {
        return (
            <div className="device_card graph-container" id="rack-graph-id">
                <Row>
                    <Col sm={3} md={4} lg={4} xl={2}>
                        <div style={{ padding: 12 }}>
                            <h6 className="cmmb-memory-heading">
                                {title} <span style={{ color: "white" }}>Usage</span>
                            </h6>
                        </div>
                    </Col>
                    <Col sm={3} md={8} lg={8} xl={10}>
                        <LoadingSpinner height={150} />
                    </Col>
                </Row>
            </div>
        );
    }

    return (
        <div className="device_card graph-container" id="rack-graph-id">
            <Row>
                <Col sm={3} md={4} lg={4} xl={2}>
                    <div style={{ padding: 12 }}>
                        <h6 className="cmmb-memory-heading">
                            {title} <span style={{ color: "white" }}>Usage</span>
                        </h6>
                    </div>
                </Col>
                <Col sm={3} md={8} lg={8} xl={10} data-testid="rackBandwidth-id">
                    <Chart
                        data-testid="chart"
                        chartType="AreaChart"
                        width="100%"
                        height="150px"
                        data={memoryData}
                        options={getCmmbMemoryDataOptions()}
                    />
                </Col>
            </Row>
        </div>
    );
};
MemoryUsageChart.propTypes = {
    viewMode: PropTypes.oneOf([VIEW_MODES.CMMB, VIEW_MODES.HOST]).isRequired,
    memoryData: PropTypes.arrayOf(
        PropTypes.arrayOf(
            PropTypes.oneOfType([PropTypes.string, PropTypes.number])
        )
    ).isRequired,
    isLoading: PropTypes.bool.isRequired
};