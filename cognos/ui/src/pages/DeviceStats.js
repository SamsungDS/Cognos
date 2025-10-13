import React, {useState} from 'react';
import PropTypes from 'prop-types';
import DeviceCard from '../components/device-Stats/deviceCard';
import './deviceStats.css';
const Card = ({ selectedMetrics, setSelectedMetrics }) => {
    return(
        <div className='card rounded border-1 shadow-sm' style={{ height: '30rem', backgroundColor: "black"}}>
            <DeviceCard selectedMetrics={selectedMetrics} setSelectedMetrics={setSelectedMetrics} />
        </div>
    )
}
const DeviceStats = () => {
    const [selectedMetrics, setSelectedMetrics] = useState({
            'CXL Capacity': 'total_memory_MB',         
    });
    const [selectedMetrics1, setSelectedMetrics1] = useState({
        'CXL Usage': 'used_memory_MB'
    });
    const [selectedMetrics2, setSelectedMetrics2] = useState({
        'CXL Bandwidth': 'total_bandwidth_MBps'
    });
    const [selectedMetrics3, setSelectedMetrics3] = useState({
        'CXL Temperature': 'fpga_temp_in_F'
    });
    
    return (
        <div className = "custom-container">
            <div className='row g-4 mb-1 p-3 pb-0'>
                <div className='col-6'><Card selectedMetrics={selectedMetrics} setSelectedMetrics={setSelectedMetrics}/></div>
                <div className='col-6'><Card selectedMetrics={selectedMetrics1} setSelectedMetrics={setSelectedMetrics1} /></div>
            </div> 
            <div className='row g-4 mb-1 p-3'>
                <div className='col-6'><Card selectedMetrics={selectedMetrics2} setSelectedMetrics={setSelectedMetrics2} /></div>
                <div className='col-6'><Card selectedMetrics={selectedMetrics3} setSelectedMetrics={setSelectedMetrics3} /></div>
            </div>        
        </div>
    )
};
Card.propTypes = { 
    selectedMetrics: PropTypes.bool,
    setSelectedMetrics: PropTypes.bool
}
export default DeviceStats;