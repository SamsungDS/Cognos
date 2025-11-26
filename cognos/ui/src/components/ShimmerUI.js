import React, { useMemo } from 'react';
import PropTypes from 'prop-types';
import './ShimmerUI.css';

const ShimmerUI = ({ type = 'host', deviceCount = 8 }) => {
    // Generate stable unique IDs for shimmer items
    const deviceIds = useMemo(() =>
        Array.from({ length: deviceCount }, (_, i) => `device-shimmer-${i}-${Date.now()}`),
        [deviceCount]
    );

    const badgeIds = useMemo(() =>
        Array.from({ length: 4 }, (_, i) => `badge-shimmer-${i}-${Date.now()}`),
        []
    );

    if (type === 'host') {
        return (
            <div className="shimmer-wrapper">
                <div className="carousel-content">
                    <div className="device-box" style={{
                        display: "flex",
                        justifyContent: "center",
                        alignItems: "center",
                    }}>
                        <div className="shimmer-device-container">
                            {deviceIds.map((id) => (
                                <div key={id} className="shimmer-device-wrapper">
                                    <div className="shimmer shimmer-device-icon" />
                                    <div className="shimmer shimmer-device-label" />
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    if (type === 'cmm-b') {
        return (
            <div className="shimmer-wrapper">
                <div className="carousel-content">
                    <div className="shimmer-badge-container">
                        {badgeIds.map((id) => (
                            <div key={id}>
                                <div className="shimmer shimmer-host-badge" />
                                <div className="shimmer-vertical-line" />
                            </div>
                        ))}
                    </div>
                    <div className="device-box" style={{
                        display: "flex",
                        justifyContent: "center",
                        alignItems: "center",
                    }}>
                        <div className="shimmer-device-container">
                            {deviceIds.map((id) => (
                                <div key={id} className="shimmer-device-wrapper">
                                    <div className="shimmer shimmer-device-icon" />
                                    <div className="shimmer shimmer-device-label" />
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return null;
};

ShimmerUI.propTypes = {
    type: PropTypes.oneOf(['host', 'cmm-b']),
    deviceCount: PropTypes.number
};

ShimmerUI.defaultProps = {
    type: 'host',
    deviceCount: 8
};

export default ShimmerUI;

// Create NavigationShimmer component in ShimmerUI.js
export const NavigationShimmer = ({ tabCount = 6 }) => {
    // Generate stable unique IDs for tabs
    const tabIds = useMemo(() =>
        Array.from({ length: tabCount }, (_, i) => `tab-shimmer-${i}-${Date.now()}`),
        [tabCount]
    );

    return (
        <div className="shimmer-navigation">
            {/* Left Arrow Shimmer */}
            <div className="shimmer-arrow"></div>

            {/* Title Tabs Shimmer */}
            {tabIds.map((id) => (
                <div key={id} className="shimmer-title-tab"></div>
            ))}

            {/* Right Arrow Shimmer */}
            <div className="shimmer-arrow"></div>
        </div>
    );
};

NavigationShimmer.propTypes = {
    tabCount: PropTypes.number
};

NavigationShimmer.defaultProps = {
    tabCount: 6
};