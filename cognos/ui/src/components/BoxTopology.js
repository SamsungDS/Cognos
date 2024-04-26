import React, {useEffect, useState} from 'react';
import { Container, Row, Col, Badge} from 'react-bootstrap';
import 'rc-slider/assets/index.css';
import './BoxTopology.css';
import { Configs, ArrowLeft, ArrowRight, cxlDevArrow, 
    HostIconInactive, cxlDevIconInActive, cxlDevArrowInactive,
    Host1, Host2, Host3, Host4, Host5, Host6, Host7, Host8, 
    D1, D2, D3, D4, D5, D6, D7, D8 } from '../constant';

const BoxTopology = () => {

    const [hostToDeviceMapping, setHostToDeviceMapping] = useState([]);
    const hostDeviceMapEndpoint = Configs.data_endpoint + "/host_device_map"
    useEffect(() => {
      fetch(hostDeviceMapEndpoint)
          .then(response => response.json())
          .then(data => setHostToDeviceMapping(data));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []);
    console.log(hostToDeviceMapping)

    const HostList = [
        {
          host: 'Host1',
          srcImage: {Host1},
          color: '#0077C8'      
        },
        {
          host: 'Host2',
          srcImage: {Host2},
          color: '#AC55FF'
        },
        {
          host: 'Host3',
          srcImage: {Host3},
          color: '#00B3E3'
        },
        {
          host: 'Host4',
          srcImage: {Host4},
          color: '#8093DC'
        },
        {
          host: 'Host5',
          srcImage: {Host5},
          color: '#FFB546'
        },
        {
          host: 'Host6',
          srcImage: {Host6},
          color: '#FF6700'
        },
        {
          host: 'Host7',
          srcImage: {Host7},
          color: '#00C3B2'
        },
        {
          host: 'Host8',
          srcImage: {Host8},
          color: '#52DD3A'
        }
      ] 
    const DeviceList = [
        {
          lmd: 'D1'
        },
        {
          lmd: 'D2'   
        },
        {
          lmd: 'D3'
        },
        {
          lmd: 'D4'
        },
        {
          lmd: 'D5'
        },
        {
          lmd: 'D6'
        },
        {
          lmd: 'D7'
        },
        {
          lmd: 'D8'
        }
      ] 

    const mappedHostList = HostList.map(item => {
      const isActive = hostToDeviceMapping.some(hostItem => hostItem.host === item.host);
        return {
          ...item,
          color: isActive ? item.color : '#4F4F4F',
          isActive
        };
    });
  

    const mappedDeviceList = DeviceList.map(device => {
      const associatedHost = hostToDeviceMapping.find(host => host.devices.includes(device.lmd));
      const hostDetails = associatedHost ? HostList.find(h => h.host === associatedHost.host) : null;
      return {
        ...device,
        color: hostDetails ? hostDetails.color : '#4F4F4F',
        hostDetails,
      };
    });
  

    const numbers = [];

    for (let i = 1; i <= 19; i++) {
        numbers.push(`${i}`);
    }

    // Hosts rendering
    const hostComponents = mappedHostList.map((host, index) => {
      const part = host.host.split('');
      const lineColor = host.color;
      const result = part[4];
      const dynamicStyle = {
        color: host.isActive ? host.color : '#4F4F4F',
        border: host.isActive ? `2px solid ${host.color}` : '2px solid #4F4F4F',
      };
      const srcImage = host.isActive ? host.srcImage[host.host]: HostIconInactive;
  
      const Metadata = (
        `name: Host ${result} LNK0,
        port: 3,
        port_type: CXL_11,
        PCIe_version: 5,
        PCIe_lanes: 8,
        `
    ).replace(/ +/g, '');
    const lineStyle = { 
      background: host.isActive ? 'white' : '#4F4F4F',
      marginBottom: '8px'
    };
      return (
        <div key={result}>
          <div>
            <Badge className='badge' style={dynamicStyle} title={Metadata}>
              <span className='vertical-badge-line' style={{color:lineColor, fontWeight:900}}>| | | </span>
              <span className='badge-name' style={{paddingTop:4, fontFamily: 'samsung sharp sons',}}>&nbsp; {`H-${result}`} &nbsp;&nbsp;</span>
              <img className='host-round-icon' src={srcImage} alt="HostIcon" style={{ objectFit: 'contain', fontFamily: 'Samsung' }} />
            </Badge>
            <div>
              <div className='vertical-line' style={lineStyle}></div>
            </div>
          </div>
        </div>
        )
    });
    const hostColorsIcon = mappedHostList.map((host) => {
      const part = host.host.split('');
      const lineColor = host.color;
      const result = part[4];
      const Metadata = (
        `name: Host ${result} LNK0,
        port: 3,
        port_type: CXL_11,
        PCIe_version: 5,
        PCIe_lanes: 8,
        `
    ).replace(/ +/g, '');
      return (
        <div key={result}>
          <p style={{color:'white', backgroundColor: lineColor}} title={Metadata} className='circle-solid solid'></p>
        </div>
        )
    });
    const getImageByColor = (colorCode) => {
      const colorImageMap = {
        '#0077C8': D1, 
        '#00B3E3': D2,
        '#52DD3A': D3,
        '#FF6700': D4,
        '#AC55FF': D5,
        '#8093DC': D6,
        '#00C3B2': D7,
        '#FFB546': D8       
      };
      return colorImageMap[colorCode];
    }

    // CXL Devices rendering
    const cxlDeviceComponents = mappedDeviceList.map((device) => {
      const part = device.lmd.split('');
      const fontColor = device.color;
      const result = part[1];
      const srcImage = device.hostDetails ? getImageByColor(fontColor): cxlDevIconInActive;
      const D1Metadata = (
        `name: DEV_0${result}-256G
        size: 256GB
        port: 7
        dev_port_type: CXL_20
        PCIe_version: 5
        PCIe_lanes: 8
        `
    ).replace(/ +/g, '');
      
      return (
        <div className='cxl-dev' title={D1Metadata}  key={device.lmd}>
          <img src={device.hostDetails ? cxlDevArrow : cxlDevArrowInactive} alt="ArrowRight"  className='device-icon' />
          <p className='device-name' style={{color:fontColor, fontWeight:700, marginBottom:0}}>{device.lmd}</p>
          <img src={srcImage} alt="cxlDevIconActive" className='device-img' style={{ objectFit: 'contain', marginTop:0, fontFamily: 'Samsung' }} />     
          <p className='fs-22 device-Id' >{`CMM-D${result}`}</p>
        </div>
      )   
    });

    return (
        <Container className='box-container' id='topology-card-id'>
            <Row>
                <Col>
                    <div className='fs-22 cxl-switch-scroll' id='switch-scroll-id' style={{ marginBottom:4, fontFamily: 'Samsung'}}>
                        <img src={ArrowLeft} alt="ArrowLeft" className="cxl-switch-scroll-arrow" style={{ objectFit: 'contain', fontFamily: 'Samsung' }} />
                            &nbsp;&nbsp;
                            {numbers.map((number, index) => (
                            <React.Fragment key={number}>
                                {number !== '1' ? <span style={{color:'grey'}}>{number}</span> : number}
                                    {index < numbers.length - 1 && <> &nbsp;&nbsp;&nbsp; </>}
                            </React.Fragment>
                            ))}
                            &nbsp;&nbsp; 
                        <img src={ArrowRight} alt="ArrowRight"
                          className="cxl-switch-scroll-arrow" 
                          style={{ objectFit: 'contain', fontFamily: 'Samsung' }} />
                    </div>
                </Col>
            </Row>
            <Row>
                <Col>
                  <div>
                    <div className='badge-container' id='host-card-id' style={{display:'flex'}}>
                      {hostComponents}
                    </div>
                    <div className='device-box' id='cxl-device-card-id'>
                      <div className='cxl-switch-box'>
                        <div className='host-icon'>{hostColorsIcon}</div>
                        <div><p className='fs-22 cxl-switch'>CXL Switch</p></div>
                      </div>
                      <div style={{display:'flex', fontFamily: 'Samsung'}} className='cxl-device'>
                        {cxlDeviceComponents}
                      </div>
                    </div>
                  </div>
                </Col>
            </Row>
        </Container>
    )
};

export default BoxTopology;