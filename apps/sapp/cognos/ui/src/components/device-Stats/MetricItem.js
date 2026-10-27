import React from "react";
import PropTypes from 'prop-types';
import './deviceCard.css';
const MetricItem = ({ label }) => {
    return (
        <div className="metric">
            <span style={{ color: '#00B3E3', fontSize: '14px', fontWeight: "bold" }}>{label}</span>
        </div>
    );
};
MetricItem.propTypes = {
    label: PropTypes.string
}
export default MetricItem;