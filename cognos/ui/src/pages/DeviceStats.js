import React, {useState} from 'react';
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
            'CXL Capacity': true,
            'CXL Usage': true,
    });
    const [selectedMetrics1, setSelectedMetrics1] = useState({
        'CXL Usage': true,
        'CXL Bandwidth': true
    });
    return (
        <div className = "custom-container">
            <div className='row g-4 mb-1 p-3 pb-0'>
                <div className='col-6'><Card selectedMetrics={selectedMetrics} setSelectedMetrics={setSelectedMetrics}/></div>
                <div className='col-6'><Card selectedMetrics={selectedMetrics1} setSelectedMetrics={setSelectedMetrics1} /></div>
            </div> 
            <div className='row g-4 mb-1 p-3'>
                <div className='col-6'><Card selectedMetrics={selectedMetrics} setSelectedMetrics={setSelectedMetrics} /></div>
                <div className='col-6'><Card selectedMetrics={selectedMetrics1} setSelectedMetrics={setSelectedMetrics1} /></div>
            </div>        
        </div>
    )
};
export default DeviceStats;