import React from "react";
import './deviceCard.css';
const MetricItem = ({ label }) => {
    const colors = {
        'CXL Capacity': '#FFB546',
        'CXL Usage': '#0077C8',
        'CXL Bandwidth': '#00C3B2'
    };

    return (
        <div style={{
            padding: '8px 12px',
            marginBottom: '8px',
            backgroundColor: '#2a2a2a',
            borderRadius: '4px',
            display: 'flex',
            alignItems: 'center'
        }}>
            <div style={{
                width: '12px',
                height: '12px',
                backgroundColor: colors[label] || '#888',
                borderRadius: '2px',
                marginRight: '10px'
            }} />
            <span style={{ color: '#ccc', fontSize: '14px' }}>{label}</span>
        </div>
    );
};
export default MetricItem;