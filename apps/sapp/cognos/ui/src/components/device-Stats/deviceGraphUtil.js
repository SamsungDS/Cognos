import PropTypes from 'prop-types';
import './deviceCard.css';
import MetricItem from './MetricItem';
import TreeItem from './TreeItem';

export const ErrorBanner = ({ message }) => (
    <div className="error-banner">
        {message}
    </div>
);

ErrorBanner.propTypes = {
    message: PropTypes.string.isRequired
};

export const Sidebar = ({
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
export const ChartArea = ({ selectedDevice, dimensions, containerRef, svgRef }) => (
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