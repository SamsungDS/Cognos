import React, { useContext, useState, useEffect, useRef } from "react";
import { Container, Row, Col, Spinner } from "react-bootstrap";
import Chart from "react-google-charts";
import ProgressBar from "react-bootstrap/ProgressBar";
import BoxTopology from "../components/BoxTopology";
import "./metrics.css";
import "./dashboard.css";
import "rc-slider/assets/index.css";
import * as constants from '../constant';
import { useSelectedOption } from "../contexts/SelectedOptionContext";

const Dashboard = () => {
  const { selectedOption } = useSelectedOption();
  const [version, setVersion] = useState('00.00.00');

  const apiEndpoint = constants.Configs.api_endpoint;
  // istanbul ignore next
  useEffect(() =>{
    async function getVersion() {
      try {
        const response = await fetch(`${apiEndpoint}/version`, {
          mode: 'cors',
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'Access-Control-Allow-Origin':'*'
          },
        })

        if (response.ok) {
          const data = await response.json();
          setVersion(data);
        } else {
          console.log("unable to fetch version number");
        }
      } catch (error) {
        console.log(error);
      }
    }
    getVersion()
  },
  // eslint-disable-next-line react-hooks/exhaustive-deps 
  []);

  const cmmbMemoryDataRef = useRef({});
  const [cmmbMemoryDataState, setcmmbMemoryDataState] = useState([]);
  // poll for cmmb memory data
  useEffect(() => {
    async function getCmmbMemoryUsage() {
      let payload = {};
      payload.metric_type = "cmmb_usage";
      
      const response = await constants.fetchMetrics(`${apiEndpoint}/metrics`, payload);

      if (response?.ok) {
          const data = await response.json();
          cmmbMemoryDataRef.current = data;
          setcmmbMemoryDataState(cmmbMemoryDataRef.current);
      }
      else {
          console.log("unable to fetch memory cpu data..");
      }
    }

    getCmmbMemoryUsage()
    const interval = setInterval(() => getCmmbMemoryUsage(), 3000)
    return () => {
      clearInterval(interval);
    }
  }, [])

  const cmmbCapacityDataRef = useRef({});
  const [cmmbCapacityDataState, setcmmbCapacityDataState] = useState([]);
  // poll for cmmb capacity data
  useEffect(() => {
    async function getCmmbCapacityUsage() {
      let payload = {};
      payload.metric_type = "cmmb_capacity";
      
      const response = await constants.fetchMetrics(`${apiEndpoint}/metrics`, payload);

      if (response?.ok) {
          const data = await response.json();
          cmmbCapacityDataRef.current = data;
          setcmmbCapacityDataState(cmmbCapacityDataRef.current);
      }
      else {
          console.log("unable to fetch memory cpu data..");
      }
    }

    getCmmbCapacityUsage()
    const interval = setInterval(() => getCmmbCapacityUsage(), 3000)
    return () => {
      clearInterval(interval);
    }
  }, [])

  const cmmbBandwidthDataRef = useRef({});
  const [cmmbBandwidthDataState, setCmmbBandwidthDataState] = useState([]);
  // poll for cmmb bandwidth usage
  useEffect(() => {
    async function getCmmbBandwidthUsage() {
      let payload = {};
      payload.metric_type = "cmmb_bandwidth";

      const response = await constants.fetchMetrics(`${apiEndpoint}/metrics`, payload);

      if (response?.ok) {
          const data = await response.json();
          cmmbBandwidthDataRef.current = data;
          setCmmbBandwidthDataState(cmmbBandwidthDataRef.current);
      }
      else {
          console.log("unable to fetch memory cpu data..");
      }
    }

    getCmmbBandwidthUsage()
    const interval = setInterval(() => getCmmbBandwidthUsage(), 3000)
    return () => {
      clearInterval(interval);
    }
  }, [])

  const devicesCountDataRef = useRef({});
  const [devicesCountDataState, setdevicesCountDataState] = useState([]);
  // poll for devices count
  useEffect(() => {
    async function getDevicesCount() {
      let payload = {};
      payload.metric_type = "devices_count";
      
      const response = await constants.fetchMetrics(`${apiEndpoint}/metrics`, payload);

      if (response?.ok) {
          const data = await response.json();
          devicesCountDataRef.current = data;
          setdevicesCountDataState(devicesCountDataRef.current);
      }
      else {
          console.log("unable to fetch memory cpu data..");
      }
    }

    getDevicesCount()
    const interval = setInterval(() => getDevicesCount(), 3000)
    return () => {
      clearInterval(interval);
    }
  }, [])


  const cmmbMemoryDataOptions = {
    isStacked: true,
    height: 180,
    titleTextStyle: { color: "#FFFFFD", fontSize: 25, bold: true },
    colors: ["#00B3E3"],
    hAxis: {
      title: "Time",
      textStyle: { color: "#FFFFFD" },
      titleTextStyle: { color: "#FFFFFD" },
      gridlines: { color: "#4C4C3B" },
    },
    vAxis: {
      minValue: 100,
      title: "Usage (MB)",
      textStyle: { color: "#FFFFFD" },
      titleTextStyle: { color: "#FFFFFD" },
    },
    curveType: "function",
    lineWidth: 5,
    chartArea: { width: "70%", height: "100%", top: 50, bottom: 50 },
    backgroundColor: { fill: "transparent" },
    animation: { startup: true },
    annotations: {
      textStyle: {
        fontName: "Times-Roman",
        fontSize: 18,
        bold: true,
        italic: true,
        color: "#FFFFFD",
        auraColor: "#FFFFFD",
        opacity: 0.8,
      },
    },
    legend: { textStyle: { color: "#FFFFFD" } },
  };

  return (
    <div className="Content content_root" id="dashboard-container-id">
      <Container fluid>
        <Row>
          <Col>
            <div
              className="device_card memory-box-overview-height"
              data-testid="memory-box-overview"
              id="memory-box-overview-id"
            >
              <h4 className="memory-box-title">MEMORY BOX OVERVIEW</h4>
            </div>
          </Col>
        </Row>
        <Row>
          <Col sm={12} md={12} lg={12} xl={8}>
            <div
              className="device_card topology-height"
              data-testid="box-topology-id"
              id="box-topology-id"
            >
              <BoxTopology />
            </div>
          </Col>
          <Col sm={12} md={12} lg={12} xl={4}>
            {selectedOption === "Host" ? (
              <>
                <div className="device_card info-memo-com">
                  <div className="spinner-style" style={{ height: 150 }}>
                    <div
                      style={{
                        color: "white",
                        textAlign: "center",
                      }}
                    >
                      This data is not available for this host
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <>
                {devicesCountDataState.num_hosts ? (
                  <div
                    className="device_card info-memo-com"
                    id="mem-info"
                    style={{ fontFamily: "Samsung One", verticalAlign: "top" }}
                  >
                    <Row className="row-info-memo">
                      <Col>
                        <div
                          style={{
                            color: "white",
                            display: "inline",
                            fontWeight: "bold",
                          }}
                        >
                          {" "}
                          Attached Hosts &nbsp;{" "}
                        </div>
                      </Col>
                      <Col>
                        <span className="arrow">
                          <i className="right"></i>
                        </span>
                      </Col>
                      <Col>
                        <span
                          className="circle"
                          style={{ color: "#00B3E3" }}
                        >{`${
                          devicesCountDataState.num_hosts
                            ? devicesCountDataState.num_hosts
                            : 0
                        }`}</span>
                      </Col>
                    </Row>
                    <Row className="row-info-memo">
                      <Col>
                        <div
                          style={{
                            color: "white",
                            display: "inline",
                            fontWeight: "bold",
                          }}
                        >
                          {" "}
                          CXL Devices{" "}
                        </div>
                      </Col>
                      <Col>
                        <span className="arrow">
                          <i className="right"></i>
                        </span>
                      </Col>
                      <Col>
                        <div
                          className="circle"
                          style={{ color: "#00B3E3" }}
                        >{`${
                          devicesCountDataState.num_cxl_devices
                            ? devicesCountDataState.num_cxl_devices
                            : 0
                        }`}</div>
                      </Col>
                    </Row>
                  </div>
                ) : (
                  <div className="device_card info-memo-com" id="mem-info">
                    <div className="spinner-style" style={{ height: 150 }}>
                      <Spinner animation="border" variant="secondary" />
                    </div>
                  </div>
                )}
              </>
            )}
            <Row>
              <Col>
                <div
                  className="device_card system-memory-allocated"
                  id="sys-mem-allocated-id"
                >
                  {selectedOption === "Host" ? (
                    <>
                      <div className="spinner-style" style={{ height: 150 }}>
                        <div
                          style={{
                            color: "white",
                            textAlign: "center",
                          }}
                        >
                          This data is not available for this host
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div
                        style={{
                          color: "white",
                          fontWeight: "bold",
                          fontFamily: "Samsung",
                        }}
                      >
                        <h4 className="cmmb-memory-heading">
                          CMM-B <span style={{ color: "white" }}>Capacity</span>
                        </h4>
                      </div>
                      <div>
                        {cmmbCapacityDataState.total_capacity ? (
                          <div style={{ paddingTop: 12 }}>
                            <div
                              className="progres-bar-label"
                              style={{ color: "white" }}
                            >
                              {`${
                                cmmbCapacityDataState.total_capacity
                                  ? cmmbCapacityDataState.total_capacity
                                  : 0
                              } GB`}
                            </div>
                            <ProgressBar
                              style={{ height: 24, fontWeight: "bold" }}
                              now={cmmbCapacityDataState.used_capacity_percentage}
                              key={1}
                              className="host1"
                            />
                            <div
                              style={{ color: "white", marginLeft: 200 }}
                            >{`Used Capacity ${
                              cmmbCapacityDataState.used_capacity
                                ? cmmbCapacityDataState.used_capacity
                                : 0
                            } GB`}</div>
                          </div>
                        ) : (
                          <div
                            className="spinner-style"
                            style={{ height: 150 }}
                          >
                            <Spinner animation="border" variant="secondary" />
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </Col>
            </Row>
          </Col>
        </Row>
        <Row>
          <Col sm={12} md={12} lg={12} xl={8}>
            <div className="device_card graph-container" id="rack-graph-id">
              {selectedOption === "Host" ? (
                <>
                  <div className="spinner-style" style={{ height: 150 }}>
                    <div
                      style={{
                        color: "white",
                        textAlign: "center",
                        marginTop: 50,
                      }}
                    >
                      This data is not available for this host
                    </div>
                  </div>
                </>
              ) : (
                <Row>
                  <Col sm={3} md={4} lg={4} xl={2}>
                    <div style={{ padding: 12 }}>
                      <h6 className="cmmb-memory-heading">
                        CMM-B Memory{" "}
                        <span style={{ color: "white" }}>Usage</span>
                      </h6>
                    </div>
                  </Col>
                  <Col
                    sm={3}
                    md={8}
                    lg={8}
                    xl={10}
                    data-testid="rackBandwidth-id"
                  >
                    {cmmbMemoryDataState?.length > 1 ? (
                      <Chart
                        data-testid="chart"
                        chartType="AreaChart"
                        width="100%"
                        height="150px"
                        data={cmmbMemoryDataState}
                        options={cmmbMemoryDataOptions}
                      />
                    ) : (
                      <div
                        className="spinner-style"
                        style={{ height: 150, marginTop: 40 }}
                      >
                        <Spinner animation="border" variant="secondary" />
                      </div>
                    )}
                  </Col>
                </Row>
              )}
            </div>
          </Col>
          <Col sm={12} md={12} lg={12} xl={4}>
            <div
              className="device_card system-memory-allocated"
              id="sys-mem-allocated-id"
            >
              {selectedOption === "Host" ? (
                <>
                  <div
                    style={{
                      color: "white",
                      textAlign: "center",
                      marginTop: 65,
                    }}
                  >
                    This data is not available for this host
                  </div>
                </>
              ) : (
                <>
                  <div
                    style={{
                      color: "white",
                      fontWeight: "bold",
                      fontFamily: "Samsung",
                    }}
                  >
                    <h4 className="cmmb-memory-heading">
                      CMM-B Memory{" "}
                      <span style={{ color: "white" }}>Bandwidth</span>
                    </h4>
                  </div>
                  <div>
                    {cmmbBandwidthDataState.max_bandwidth ? (
                      <div style={{ paddingTop: 12 }}>
                        <div
                          className="progres-bar-label"
                          style={{ color: "white" }}
                        >
                          {`${
                            cmmbBandwidthDataState.max_bandwidth
                              ? cmmbBandwidthDataState.max_bandwidth
                              : 0
                          } GBps`}
                        </div>
                        <ProgressBar
                          style={{ height: 24, fontWeight: "bold" }}
                          now={cmmbBandwidthDataState.used_percentage_bandwidth}
                          key={1}
                          className="host1"
                        />
                        <div
                          style={{ color: "white", marginLeft: 200 }}
                        >{`Used Bandwidth ${
                          cmmbBandwidthDataState.used_bandwidth
                            ? cmmbBandwidthDataState.used_bandwidth
                            : 0
                        } GBps`}</div>
                      </div>
                    ) : (
                      <div className="spinner-style" style={{ height: 150 }}>
                        <Spinner animation="border" variant="secondary" />
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </Col>
        </Row>
        <Row>
          <Col>
            <div
              className="device_card memory-box-overview-height text-center"
            >
              <h4 className="memory-box-title1">Samsung Cognos Management Console ({version.version})</h4>
            </div>
          </Col>
        </Row>
      </Container>
    </div>
  );
};

export default Dashboard;
