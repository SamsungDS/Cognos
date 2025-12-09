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
        // istanbul ignore next
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
    // istanbul ignore next
    const calculateMemoryPerCore = () => {
        if (!memCapacityData || memCapacityData.length <= 1) return null;

        // Find DRAM capacity from memCapacityData
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

        // Calculate (total (cxl+dram) capacity / dram capacity)
        if (dramCapacity > 0) {
            const totalCapacity = cxlCapacity + dramCapacity;
            const multiplier = totalCapacity / dramCapacity;
            return multiplier.toFixed(1); // One decimal place
        }

        return null;
    };

    // Transform memCapacityData for the pie chart tooltip/legend
    // Keep numeric values in GB for the chart, but we'll update the options for display
    // istanbul ignore next
    const getTransformedMemCapacityData = () => {
        if (!memCapacityData || memCapacityData.length <= 1) return memCapacityData;

        // Chart needs numeric values, so keep them in GB
        // We'll handle TB conversion in the chart options formatter
        return memCapacityData;
    };

    // Update chart options to show TB in tooltips and labels
    // istanbul ignore next
    const getUpdatedMemCapacityOptions = () => {
        const baseOptions = getMemCapacityOptions();

        return {
            ...baseOptions,
            tooltip: { trigger: 'none' },
            text: 'percentage',
            pieSliceText: 'percentage',
            pieSliceTextStyle: {
                ...baseOptions?.pieSliceTextStyle,
                fontSize: 14
            }
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
                        <div style={{ color: "white", marginLeft: 200 }}>
                            {`Used Memory ${usedCapacityDisplay}`}
                        </div>
                    </>
                ) : (
                    <>
                        <div style={{ display: "flex", alignItems: "center" }}>
                            {/* Memory per core display - Left side */}
                            {memoryPerCore && (
                                <div style={{
                                    color: "white",
                                    fontSize: "40px",
                                    fontWeight: "bold",
                                    marginRight: "30px",
                                    marginLeft: "5px",
                                    textAlign: "center"
                                }}>
                                    <div style={{ fontSize: "40px", color: "#4CAF50" }}>
                                        {memoryPerCore}x
                                    </div>
                                    <div style={{ fontSize: "12px", marginTop: "5px" }}>
                                        more memory<br />per core
                                    </div>
                                </div>
                            )}

                            {/* Pie Chart */}
                            <div style={{ flex: 1 }}>
                                <Chart
                                    chartType="PieChart"
                                    data={getTransformedMemCapacityData()}
                                    options={getUpdatedMemCapacityOptions()}
                                    width="80%"
                                    height="250px"
                                    style={{ marginTop: "-40px", marginLeft: "5px" }}
                                />
                            </div>
                        </div>

                        {/* Custom legend with TB values */}
                        <div style={{
                            color: "white",
                            marginTop: "-123px",
                            marginLeft: "22rem",
                            fontSize: "12px"
                        }}>
                            {memCapacityData?.slice(1).map((item, idx) => (
                                <div key={idx} style={{ marginBottom: "5px" }}>
                                    <strong>{item[0]}:</strong> {formatCapacity(item[1])}
                                </div>
                            ))}
                        </div>
                    </>
                )}
                <div className="progres-bar-label" style={{ color: "white", marginTop: isCMMB ? "-100px" : "10px", marginLeft: isCMMB ? "-100px" : "22rem", }}>
                    {`Total: ${totalCapacityDisplay}`}
                </div>
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