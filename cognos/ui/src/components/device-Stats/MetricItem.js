import React from "react";
import PropTypes from 'prop-types';
import './deviceCard.css';
const MetricItem = ({ label }) => {
    return (
        <div className="metric">
            <span style={{ color: '#ccc', fontSize: '14px' }}>{label}</span>
        </div>
    );
};
MetricItem.propTypes = {
    label: PropTypes.string
}
export default MetricItem;