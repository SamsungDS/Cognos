import React, {useEffect, useState} from 'react';
import { Container, Row, Col, Badge, Carousel} from 'react-bootstrap';
import 'rc-slider/assets/index.css';
import './BoxTopology.css';
import { Configs, ArrowLeft, ArrowRight,
    HostIconInactive, cxlDevIconInActive,
    Host1, Host2, Host3, Host4, Host5, Host6, Host7, Host8, DeviceList, DeviceList1,
    getImageByColor } from '../constant';


const BoxTopology = () => {

    const [hostToDeviceMapping, setHostToDeviceMapping] = useState([]);
    const [hostToDeviceMappingB2, setHostToDeviceMappingB2] = useState([]);
    const [currentCMM, setCurrentCMM] = useState(0);
    const hostDeviceMapEndpoint = Configs.api_endpoint + "/topology"
    useEffect(() => {
      fetch(hostDeviceMapEndpoint , {
        method: 'get',
        headers: new Headers({
          'Access-Control-Allow-Origin':'*'
        })
      })
          .then(response => response.json())
          .then(data => setHostToDeviceMapping(data))
          .catch(err => {console.log(err)});
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []);
    console.log(hostToDeviceMapping)

    const HostList = [
        {
          host: 'msl-cti-emr1',
          srcImage: {Host1},
          color: '#0077C8'      
        },
        {
          host: 'loaner-emr02',
          srcImage: {Host2},
          color: '#AC55FF'
        },
        {
          host: 'msl-stg-emr03',
          srcImage: {Host3},
          color: '#00B3E3'
        },
        {
          host: 'Host 4',
          srcImage: {Host4},
          color: '#8093DC'
        }
      ] 
    const HostList1 = [
        {
          host: 'Host 1 LNK0',
          srcImage: {Host1},
          color: '#0077C8'      
        },
        {
          host: 'Host 2',
          srcImage: {Host2},
          color: '#AC55FF'
        },
        {
          host: 'Host 3',
          srcImage: {Host3},
          color: '#00B3E3'
        },
        {
          host: 'Host 4',
          srcImage: {Host4},
          color: '#8093DC'
        },
        {
          host: 'Host 5',
          srcImage: {Host5},
          color: '#FFB546'
        },
        {
          host: 'Host 6',
          srcImage: {Host6},
          color: '#FF6700'
        },
        {
          host: 'Host 7',
          srcImage: {Host7},
          color: '#00C3B2'
        },
        {
          host: 'Host 8',
          srcImage: {Host8},
          color: '#52DD3A'
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
      const associatedHost = hostToDeviceMapping.find(host => host.devices.includes(device.device));
      const hostDetails = associatedHost ? HostList.find(h => h.host === associatedHost.host) : null;
      return {
        ...device,
        color: hostDetails ? hostDetails.color : '#4F4F4F',
        hostDetails,
      };
    });

    const mappedHostList1 = HostList1.map(item => {
const isActive = hostToDeviceMappingB2.some(hostItem => hostItem.host === item.host);
  return {
    ...item,
    color: isActive ? item.color : '#4F4F4F',
    isActive
  };
    });


    const mappedDeviceList1 = DeviceList1.map(device => {
      const associatedHost = hostToDeviceMappingB2.find(host => host.devices.includes(device.device));
      const hostDetails = associatedHost ? HostList.find(h => h.host === associatedHost.host) : null;
      return {
        ...device,
        color: hostDetails ? hostDetails.color : '#4F4F4F',
        hostDetails,
      };
    });


    const cmmList = [
      { title: 'CMM-B1', hostComponents: mappedHostList, deviceComponents: mappedDeviceList },
      { title: 'CMM-B2', hostComponents: mappedHostList1, deviceComponents: mappedDeviceList1},
      { title: 'CMM-B3', hostComponents: mappedHostList, deviceComponents: mappedDeviceList },
      { title: 'CMM-B4', hostComponents: mappedHostList, deviceComponents: mappedDeviceList },
      { title: 'CMM-B5', hostComponents: mappedHostList, deviceComponents: mappedDeviceList },
      { title: 'CMM-B6', hostComponents: mappedHostList, deviceComponents: mappedDeviceList },
    ];
    const renderHostComponents = (hosts) => {
      return hosts.map((host, index) => {
        const shortform = host.host.split(' ')[1];
        const lineColor = host.color;
        const dynamicStyle = {
          color: host.isActive ? host.color : '#4F4F4F',
          border: host.isActive ? `2px solid ${host.color}` : '2px solid #4F4F4F',
        };
        const srcImageName = 'Host' + shortform;
        const srcImage = host.isActive ? host.srcImage[srcImageName] : HostIconInactive;
    
        const Metadata = (
          `name: ${host.host},
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
          <div key={host.host}>
            <div>
              <Badge className='badge' style={dynamicStyle} title={Metadata}>
                <span className='vertical-badge-line' style={{ color: lineColor, fontWeight: 900 }}>| | | </span>
                <span className='badge-name' style={{ paddingTop: 4, fontFamily: 'samsung sharp sons', }}>&nbsp; {`${host.host}`} &nbsp;&nbsp;</span>
                {/* <img className='host-round-icon' src={srcImage} alt="HostIcon" style={{ objectFit: 'contain', fontFamily: 'Samsung' }} /> */}
              </Badge>
              <div>
                <div className='vertical-line' style={lineStyle}></div>
              </div>
            </div>
          </div>
        );
      });
    };

    const renderDeviceComponents = (devices) => {
      return devices.map((device) => {
        const part = device.device.split('-')[0];
        const fontColor = device.color;
        const srcImage = device.hostDetails ? getImageByColor(fontColor) : cxlDevIconInActive;
        const D1Metadata = (
          `name: ${part}
          size: 256GB
          port: 7
          dev_port_type: CXL_20
          PCIe_version: 5
          PCIe_lanes: 8
          `
        ).replace(/ +/g, '');
        const deviceCount = devices.length;
        const sizeMultiplier = deviceCount > 8 ? 1 : 1.3;
        const cardStyle = {
          transform: `scale(${sizeMultiplier})`
        };
        return (
          <div className='cxl-dev' title={D1Metadata} key={device.device} style={cardStyle} >
            <p className='device-name' style={{ color: fontColor, fontWeight: 700, marginBottom: 0 }}>{part}</p>
            <img src={srcImage} alt="cxlDevIconActive" className='device-img' style={{ objectFit: 'contain', marginTop: 0, fontFamily: 'Samsung' }} />
            <p className='fs-22 device-Id' >{`${part}`}</p>
          </div>
        );
      });
    };
      // Navigation handlers
    const handlePrev = () => {
      setCurrentCMM(prevCMM => (prevCMM === 0 ? 5 : prevCMM - 1));
    };

    const handleNext = () => {
      setCurrentCMM(prevCMM => (prevCMM === 5 ? 0 : prevCMM + 1));
    };

    return (
        <Container className='box-container' id='topology-card-id'>
            <Row>
                <Col>
                  <div className='cmm-navigation'>
                  <button className='arrow-button left-arrow' onClick={handlePrev}>
                    <img src={ArrowLeft} alt="Previous" />
                  </button>
                    {cmmList.map((cmm, index) => (
                      <span
                        key={index}
                        className={`cmm-title ${index === currentCMM ? 'active' : ''}`}
                        onClick={() => setCurrentCMM(index)}
                      >
                      {cmm.title}
                      </span>
                    ))}
                    <button className='arrow-button right-arrow' onClick={handleNext}>
                      <img src={ArrowRight} alt="Next" />
                    </button>
                  </div>
                  <Carousel activeIndex={currentCMM} controls={false} indicators={false} interval={null}>
                    {cmmList.map((cmm, index) => (
                      <Carousel.Item key={index}>
                        <div className='carousel-content'>
                          <div className='badge-container' id='host-card-id' style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}>
                            {renderHostComponents(cmm.hostComponents)}
                          </div>
                          <div className='device-box' style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', }} id='cxl-device-card-id'>
                            <div className='cxl-device' style={{ display: 'flex', flexWrap: 'wrap', fontFamily: 'Samsung', textAlign: 'center', justifyContent: 'space-around' }}>
                              {renderDeviceComponents(cmm.deviceComponents)}
                            </div>
                          </div>
                        </div>
                      </Carousel.Item>
                    ))}
                  </Carousel> 
                </Col>
            </Row>
        </Container>
    )
};

export default BoxTopology;