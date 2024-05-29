import React from 'react';
import { Container, Row, Col} from 'react-bootstrap';
import  Chart from "react-google-charts";
import ProgressBar from 'react-bootstrap/ProgressBar';
import BoxTopology from '../components/BoxTopology';
import { ActiveLight, UnhealthyLight, InactiveLight } from '../constant';
import './metrics.css';
import './dashboard.css';
import 'rc-slider/assets/index.css';

const Dashboard = () => {

  const rackBandwidthData = [
    ["Memory Bandwidth", "System Bandwidth"],
    ["6", 18],
    ["5", 35],
    ["4", 61],
    ["3", 89],
    ["2", 102],
    ["Current", 118],
  ];

  const rackBandwidthOptions = {
    isStacked: true,
    height: 180,
    titleTextStyle: { color: "#FFFFFD", fontSize: 25, bold: true},
    colors: ["#00B3E3"],
    hAxis: {title: "Time Interval (<-- Minutes)", textStyle: { color: "#FFFFFD"}, titleTextStyle: { color: "#FFFFFD" }, gridlines: {color: "#4C4C3B"}},
    vAxis: {minValue: 100, title: "Mem Bandwidth GBps", textStyle: { color: "#FFFFFD"}, titleTextStyle: { color: "#FFFFFD" }},
    curveType: "function",
    
    chartArea: { width: "70%", height: "100%", top:50, bottom: 50 },
    backgroundColor: { fill:'transparent' },
    animation: {startup: true},
    annotations: {
      textStyle: {
        fontName: 'Times-Roman',
        fontSize: 18,
        bold: true,
        italic: true,
        // The color of the text.
        color: '#FFFFFD',
        // The color of the text outline.
        auraColor: '#FFFFFD',
        // The transparency of the text.
        opacity: 0.8
      }
    },
    legend: {textStyle: {color: '#FFFFFD'}},
  };

  const dramCxlMemUsageData = [
    ["Mem Usage", "CMM-D"],
    ["50 sec", 74],
    ["40 sec", 71],
    ["30 sec", 118],
    ["20 sec", 84],
    ["10 sec", 103],
    ["1 sec", 67],
  ];
  const dramCxlMemUsageOptions = {
    isStacked: true,
    height: 180,
    titleTextStyle: { color: "#FFFFFD", fontSize: 25, bold: true},
    colors: ["#00B3E3"],
    hAxis: {title: "Time Interval (<-- Seconds)", textStyle: { color: "#FFFFFD"}, titleTextStyle: { color: "#FFFFFD" }, gridlines: {color: "#4C4C3B"}},
    vAxis: {minValue: 100, title: "Allocation GB", textStyle: { color: "#FFFFFD"}, titleTextStyle: { color: "#FFFFFD" }},
    curveType: "function",
    chartArea: { width: "70%", height: "100%", top:20, bottom: 50 },
    backgroundColor: { fill:'transparent' },
    animation: {startup: true},
    annotations: {
      textStyle: {
        fontName: 'Times-Roman',
        fontSize: 18,
        bold: true,
        italic: true,
        // The color of the text.
        color: '#FFFFFD',
        // The color of the text outline.
        auraColor: '#FFFFFD',
        // The transparency of the text.
        opacity: 0.8
      }
    },
    legend: {textStyle: {color: '#FFFFFD'}}
  };

  return (
      <div className='Content content_root' id='dashboard-container-id'>
        <Container fluid>
          <Row>
            <Col sm={12} md={12} lg={12} xl={8}>
              <div className='device_card topology-height' data-testid='box-topology-id'  id='box-topology-id'>
                <BoxTopology/>
              </div>
            </Col>
            <Col sm={12} md={12} lg={12} xl={4}>
              <div className='device_card info-memo-com' id='mem-info' style={{ fontFamily: 'Samsung', verticalAlign: 'top'}}>
                <Row className='row-info-memo'>
                  <Col className='info-memo'>
                    <div style={{color: 'white', display: 'inline'}}> Hosts &nbsp; <div className="circle" style={{color:'#AC55FF'}}>2</div></div>
                  </Col>
                  <Col className='info-memo'>
                    <div style={{color: 'white', display: 'inline'}}> CMM &nbsp; <div className="circle" style={{color:'#00B3E3'}}>6</div></div>
                  </Col>     
                  <Col className='info-memo'>
                    <div style={{color: 'white', display: 'inline' }}> Racks &nbsp; <div className="circle" style={{color:'#52DD3A'}}>1</div></div>
                  </Col>                 
                </Row>
              </div>
              <Row>
                <Col>
                  <div className='device_card system-memory-allocated' id='sys-mem-allocated-id'> 
                    <div style={{color: 'white', fontWeight: 'bold', fontFamily: 'Samsung'}}>System Memory Allocated</div>
                    <div>
                      <div style={{color: 'white', paddingTop:12}}>
                        CMM-D
                      </div>
                      <div style={{paddingTop:12}}>
                        <ProgressBar style={{ height: 12, fontWeight: 'bold'}} now='66' label='1 TB' key={1} className='host1'/>
                        <div className='progres-bar-label' style={{color:'white', marginLeft:388}}>1.5 TB</div>
                      </div>
                    </div>
                    <div>
                      <div style={{color: 'white', paddingTop:12}}>
                          CMM-H
                      </div>
                      <div style={{paddingTop:12}}>
                          <ProgressBar style={{ height: 12, fontWeight: 'bold', fontSize:12}} now='0' label='0 GB' className='host2'/>
                          <div className='progres-bar-label' style={{color:'white', marginLeft:388}}>0 TB</div>
                      </div>
                    </div>
                  </div>
                </Col>
              </Row>
              <div  className='device_card health-container' id='health-container-id' style={{ padding: 24, fontFamily: 'Samsung'}}>
                  <Row>                      
                    <Col style={{color: 'white'}} sm={3} md={3} lg={3}> Health</Col>
                    <Col sm={9} md={9} lg={9}>
                      <Row>
                        <Col style={{color: 'white'}}>CMM-D</Col>
                        <Col style={{color: 'white'}}><img title="Failure: see Configure page for more details" alt='activelight' src={UnhealthyLight} width="20" height="auto" style={{objectFit: "cover", cursor:'pointer'}} />&nbsp; 0</Col>
                        <Col style={{color: 'white'}}><img title="Healthy: see Configure page for more details" src={ActiveLight} alt='activelight' width="20" height="auto" style={{objectFit: "cover", cursor:'pointer'}} />&nbsp; 6</Col>
                        <Col style={{color: 'white'}}><img title="Warning: see Configure page for more details" src={InactiveLight} alt='Inactivelight' width="20" height="auto" style={{objectFit: "cover", cursor:'pointer'}} />&nbsp; 0</Col>
                      </Row>
                      <Row>
                        <Col style={{color: 'white'}}>Host</Col>
                        <Col style={{color: 'white'}}><img title="Failure: see Configure page for more details" alt='activelight' src={UnhealthyLight} width="20" height="auto" style={{objectFit: "cover", cursor:'pointer'}} />&nbsp; 0</Col>
                        <Col style={{color: 'white'}}><img title="Healthy: see Configure page for more details" src={ActiveLight} alt='activelight' width="20" height="auto" style={{objectFit: "cover", cursor:'pointer'}} />&nbsp; 2</Col>
                        <Col style={{color: 'white'}}><img title="Warning: see Configure page for more details" src={InactiveLight} alt='activelight' width="20" height="auto" style={{objectFit: "cover", cursor:'pointer'}} />&nbsp; 0</Col>
                      </Row>
                    </Col>
                  </Row>
              </div>
            </Col>
          </Row>
          <Row>
            <Col sm={12} md={12} lg={12} xl={6}>
              <div className='device_card graph-container' id='rack-graph-id'>
                <Row>
                  <Col sm={3} md={3} lg={3}>
                    <div className='fs-22' style={{padding: 12}}>
                      <h6>Trend Graph</h6>
                      <h6 style={{fontWeight: 'bold'}}>System Bandwidth</h6>
                    </div>
                  </Col>
                </Row>
                <Row>
                  <Col data-testid='rackBandwidth-id'>
                    <Chart
                      data-testid='chart'
                      chartType='AreaChart'
                      width="100%"
                      height="150px"
                      data={rackBandwidthData}
                      options={rackBandwidthOptions}
                    />
                  </Col>
                </Row>
              </div>
            </Col>
            <Col sm={12} md={12} lg={12} xl={6}>
              <div className='device_card graph-container' id='cmm-graph-id'>
                <Row>
                  <Col sm={3} md={3} lg={3}>
                    <div className='fs-22' style={{padding: 12}}>
                      <h6>Trend Graph</h6>
                      <h6 style={{fontWeight: 'bold'}}>CMM-D</h6>
                    </div>
                  </Col>
                </Row>  
                <Row>
                  <Col data-testid='dramCxlMemUsage-id'>
                    <Chart
                      chartType='AreaChart'
                      width="100%"
                      height="150px"
                      data={dramCxlMemUsageData}
                      options={dramCxlMemUsageOptions}
                    />
                  </Col>
                </Row>                     
              </div>
            </Col>
          </Row>
        </Container>
      </div>
  )
}

export default Dashboard