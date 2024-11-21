import React, { useContext, useState, useEffect } from "react";
import { Container, Row, Col, Spinner } from "react-bootstrap";
import Chart from "react-google-charts";
import ProgressBar from "react-bootstrap/ProgressBar";
import BoxTopology from "../components/BoxTopology";
import "./metrics.css";
import "./dashboard.css";
import "rc-slider/assets/index.css";

import WebSocketContext from "../contexts/WebSocketContext";

const Dashboard = () => {
  const {
    cmmbMemoryData,
    cmmbCapacityData,
    cmmbBandwidthData,
    devicesCountData,
  } = useContext(WebSocketContext);
  const [dataAvailable, setDataAvailable] = useState(true);

  useEffect(() => {
    // Set timeout for 120 seconds (120000 ms)
    // istanbul ignore next
    const timer = setTimeout(() => {
      if (
        !cmmbBandwidthData?.max_bandwidth || !devicesCountData?.num_hosts
        || !cmmbCapacityData?.total_capacity || !cmmbMemoryData) {
          setDataAvailable(false);
      }
    }, 120000);

    // Clear timeout if data becomes available before the timeout elapses
    return () => clearTimeout(timer);
  }, [cmmbBandwidthData, devicesCountData, cmmbCapacityData, cmmbMemoryData]);

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
            {devicesCountData.num_hosts ? (
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
                    <span className="circle" style={{ color: "#00B3E3" }}>{`${
                      devicesCountData.num_hosts
                        ? devicesCountData.num_hosts
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
                    <div className="circle" style={{ color: "#00B3E3" }}>{`${
                      devicesCountData.num_cxl_devices
                        ? devicesCountData.num_cxl_devices
                        : 0
                    }`}</div>
                  </Col>
                </Row>
              </div>
            ) : dataAvailable ? (
              <div className="device_card info-memo-com" id="mem-info">
                <div className="spinner-style" style={{ height: 150 }}>
                  <Spinner animation="border" variant="secondary" />
                </div>
              </div>
            ) : (
              <div className="device_card info-memo-com" id="mem-info">
                <div className="spinner-style" style={{ height: 150 }}>
                  <div
                    style={{
                      color: "white",
                      textAlign: "center",
                      marginTop: 50,
                    }}
                  >
                    Data is not available
                  </div>
                </div>
              </div>
            )}
            <Row>
              <Col>
                <div
                  className="device_card system-memory-allocated"
                  id="sys-mem-allocated-id"
                >
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
                    {cmmbCapacityData.total_capacity ? (
                      <div style={{ paddingTop: 12 }}>
                        <div
                          className="progres-bar-label"
                          style={{ color: "white" }}
                        >
                          {`${
                            cmmbCapacityData.total_capacity
                              ? cmmbCapacityData.total_capacity
                              : 0
                          } GB`}
                        </div>
                        <ProgressBar
                          style={{ height: 24, fontWeight: "bold" }}
                          now={cmmbCapacityData.used_capacity_percentage}
                          key={1}
                          className="host1"
                        />
                        <div
                          style={{ color: "white", marginLeft: 200 }}
                        >{`Used Capacity ${
                          cmmbCapacityData.used_capacity
                            ? cmmbCapacityData.used_capacity
                            : 0
                        } GB`}</div>
                      </div>
                    ) : dataAvailable ? (
                      <div className="spinner-style" style={{ height: 150 }}>
                        <Spinner animation="border" variant="secondary" />
                      </div>
                    ) : (
                      <div className="spinner-style" style={{ height: 150 }}>
                        <div
                          style={{
                            color: "white",
                            textAlign: "center"                         
                          }}
                        >
                          Data is not available
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </Col>
            </Row>
          </Col>
        </Row>
        <Row>
          <Col sm={12} md={12} lg={12} xl={8}>
            <div className="device_card graph-container" id="rack-graph-id">
              <Row>
                <Col sm={3} md={4} lg={4} xl={2}>
                  <div style={{ padding: 12 }}>
                    <h6 className="cmmb-memory-heading">
                      CMM-B Memory <span style={{ color: "white" }}>Usage</span>
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
                  {cmmbMemoryData ? (
                    <Chart
                      data-testid="chart"
                      chartType="AreaChart"
                      width="100%"
                      height="150px"
                      data={cmmbMemoryData}
                      options={cmmbMemoryDataOptions}
                    />
                  ) : dataAvailable ? (
                    <div className="spinner-style" style={{ height: 150, marginTop: 40 }}>
                      <Spinner animation="border" variant="secondary" />
                    </div>
                  ) : (
                    <div className="spinner-style" style={{ height: 150 }}>
                      <div
                        style={{
                          color: "white",
                          textAlign: "center",
                          marginTop: 50
                        }}
                      >
                        Data is not available
                      </div>
                    </div>
                  )}
                </Col>
              </Row>
            </div>
          </Col>
          <Col sm={12} md={12} lg={12} xl={4}>
            <div
              className="device_card system-memory-allocated"
              id="sys-mem-allocated-id"
            >
              <div
                style={{
                  color: "white",
                  fontWeight: "bold",
                  fontFamily: "Samsung",
                }}
              >
                <h4 className="cmmb-memory-heading">
                  CMM-B Memory <span style={{ color: "white" }}>Bandwidth</span>
                </h4>
              </div>
              <div>
                {cmmbBandwidthData.max_bandwidth ? (
                  <div style={{ paddingTop: 12 }}>
                    <div
                      className="progres-bar-label"
                      style={{ color: "white" }}
                    >
                      {`${
                        cmmbBandwidthData.max_bandwidth
                          ? cmmbBandwidthData.max_bandwidth
                          : 0
                      } GBps`}
                    </div>
                    <ProgressBar
                      style={{ height: 24, fontWeight: "bold" }}
                      now={cmmbBandwidthData.used_percentage_bandwidth}
                      key={1}
                      className="host1"
                    />
                    <div
                      style={{ color: "white", marginLeft: 200 }}
                    >{`Used Bandwidth ${
                      cmmbBandwidthData.used_bandwidth
                        ? cmmbBandwidthData.used_bandwidth
                        : 0
                    } GBps`}</div>
                  </div>
                ) : dataAvailable ? (
                  <div className="spinner-style" style={{ height: 150 }}>
                    <Spinner animation="border" variant="secondary" />
                  </div>
                ) : (
                  <div
                    style={{
                      color: "white",
                      textAlign: "center",
                      marginTop: 65,
                    }}
                  >
                    Data is not available
                  </div>
                )}
              </div>
            </div>
          </Col>
        </Row>
      </Container>
    </div>
  );
};

export default Dashboard;