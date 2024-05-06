import React from 'react'
import { Container, Row, Col } from 'react-bootstrap';
import  Chart from "react-google-charts";
import ProgressBar from 'react-bootstrap/ProgressBar';
import DropDown from '../components/DropDown';
import * as constants from '../constant';
import './metrics.css'

const Metrics = () => {
    const selectorOptions = [
        { value: 'Host 1', label: 'Host 1' }
      ];
    // membandwidth bar
    const memBandwidthVals = ['80', '20'];

    // Total Capacity 
    const memCapacityData = [
        ["MemType", "Capacity Used"],
        ["DRAM", 1120],
        ["CMM-D", 896],
    ];

    const memCapacityOptions = {
        title: "Total Capacity per MemType (GB)",
        titleTextStyle: { color: "#FFFFFD", fontSize: 20, bold: true},
        colors: ["#B24675", "#FE5276", "#FE8E73", "#FEAE00", "B37328"],
        pieSliceText: 'value',
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
        chartArea: { width: "85%", height: "95%", top: 50, bottom: 40 },
    };

    const dramCxlMemUsageData = [
        ["Mem Usage", "DRAM", "CMM-D"],
        ["6", 123, 172],
        ["5", 151, 142],
        ["4", 481, 211],
        ["3", 831, 418],
        ["2", 996, 642],
        ["1", 1030, 795],
        ["Current", 1120, 896],
    ];

    const dramCxlMemUsageOptions = {
        isStacked: true,
        height: 220,
        title: "DRAM vs CMM-D Mem Usage",
        titleTextStyle: { color: "#FFFFFD", fontSize: 25, bold: true},
        colors: ["#24ECC5", "#EC5D24", "#00B3E3"],
        hAxis: {title: "Time Interval (<-- Minutes)", textStyle: { color: "#FFFFFD"}, titleTextStyle: { color: "#FFFFFD" }, gridlines: {color: "4C4C3B"}},
        vAxis: {minValue: 100, title: "Memory Usage (GB)", textStyle: { color: "#FFFFFD"}, titleTextStyle: { color: "#FFFFFD" }},
        curveType: "function",
        legend: {position: "bottom"},
        chartArea: { width: "65%", height: "100%", top:50, bottom: 50 },
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
        }
    };
    

  return (           
        <div className='Content content_root' id='main-container-id'>
            <Container fluid>
                <Row>
                    <Col sm={6} md={6} lg={6}>                                          
                        <div className='device_card first-row' style={{ padding:20, paddingTop:50}} id='app-server-card-id'>
                            <Row>
                                <Col sm={7} md={7} lg={7}><div className='fs-24 app-server-title'>Select Application Server</div> </Col>
                                <Col sm={5} md={5} lg={5}><div className='dropdownn-app-server'><DropDown options={selectorOptions}/></div></Col>
                            </Row>
                        </div>                                    
                    </Col>
                    <Col sm={6} md={6} lg={6}>
                        <Row>
                            <Col sm={12} md={12} lg={12}>
                                <div className='device_card first-row' id='memory-bandwidth-card-id' data-testid="memory-bandwidth-card-id">
                                    <div className='bandwidth'>
                                        <h1 className='fs-24 memory-bandwidth'>Memory Bandwidth</h1>
                                        <div>
                                            <ProgressBar style={{ height: 20, fontWeight: 'bold'}}>
                                                <ProgressBar now={memBandwidthVals[0]} label={`512 GBps`} key={1} className='host1' />
                                                <ProgressBar now={memBandwidthVals[1]} label={`64 GBps`} key={2} className='host2' />
                                            </ProgressBar>
                                        </div>
                                        <div className='bandwidth-legend'>
                                            <span className='fs-22'>
                                            <svg height={20} width={20} style={{ marginBottom: '4'}}>
                                            <circle cx="10" cy="10" r="10" stroke='black' strokeWidth={3} fill='rgb(138, 233, 138)'></circle>
                                            </svg> DRAM &nbsp;&nbsp;</span>
                                            <span  className='fs-22'>
                                            <svg height={20} width={20} style={{ marginBottom: '4'}}>
                                            <circle cx="10" cy="10" r="10" stroke='black' strokeWidth={3} fill='rgb(25, 65, 124)'></circle>
                                            </svg> CMM-D &nbsp;&nbsp;
                                            </span>                                    
                                        </div>
                                    </div>
                                </div>
                            </Col>
                        </Row>
                    </Col>
                </Row>
                <Row>
                    <Col sm={7} md={12} lg={12} xl={7}>
                        <div className='device_card second-row'  id='saphaana-card-id' style={{paddingBottom: 0, marginBottom: 0}}>
                            <div className='fs-22' style={{display: 'flex', alignItems: 'baseline', height: 30}}>
                                <h1 className='host-app-heading'>Host Application Metrics:  </h1>
                                <h1 className='sap-hana' > SAP HANA</h1>
                            </div>
                            <div style={{display: 'flex', verticalAlign: 'top', justifyContent: 'center'}}>
                                <img 
                                    src={constants.SAPHANAMetrics}
                                    alt='saphana'
                                    height='450'
                                    width='100%'
                                    title='SAP HANA Metrics'
                                />
                            </div>
                            <div style={{display: 'flex', justifyContent: 'center'}}>
                                <img
                                    src={constants.SAPHANALegend}
                                    alt='saphana1'
                                    className='saphana-legend'
                                    height='50'
                                    width='auto'
                                    title='SAP HANA Metrics Legend'
                                />
                            </div>
                        </div>
                    </Col>
                    <Col sm={5} md={12} lg={12} xl={5}>
                        <Row>
                            <Col>                            
                                <div className='device_card second-col-first-col' id='mem-capacity-data-card-id' data-testid='mem-capacity-data-card-id'>
                                    <Chart
                                        chartType='PieChart'
                                        data={memCapacityData}
                                        options={memCapacityOptions}
                                        width="100%"
                                        height="250px"
                                    />
                               </div>
                            </Col>
                        </Row>
                        <Row>
                            <Col>
                                <div className='device_card second-col-second-col' id='dram-cxl-mem-data-card-id' data-testid='dram-cxl-mem-data-card-id'>
                                    <Chart
                                        chartType='AreaChart'
                                        width="100%"
                                        height="325px"
                                        data={dramCxlMemUsageData}
                                        options={dramCxlMemUsageOptions}
                                    />
                                </div>
                            </Col>
                        </Row>
                    </Col>                    
                </Row>
            </Container>
        </div>
  )
}

export default Metrics