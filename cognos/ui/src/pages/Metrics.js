import React, { useContext, useState, useEffect, useRef } from 'react'
import { Container, Row, Col, Spinner } from 'react-bootstrap';
import  Chart from "react-google-charts";
import ProgressBar from 'react-bootstrap/ProgressBar';
import DropDown from '../components/DropDown';
import './metrics.css';
import WebSocketContext from '../contexts/WebSocketContext';
import * as constants from '../../src/constant';


export const handleSelectChange = async (
    selectedOption, setSelectedOption, setSelectorOptions,
    sendMessage, lastSelectedHost, apiEndpoint) => {
      setSelectedOption(selectedOption);

      if (selectedOption) {
        lastSelectedHost.current = selectedOption;
        sessionStorage.setItem(
          "lastSelectedHostValue",
          lastSelectedHost.current
        );
      }

      // get available hosts
      try {
        const response = await fetch(`${apiEndpoint}/hosts`, {
          mode: "cors",
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            accept: "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        });

        if (response.ok) {
          const data = await response.json();
          setSelectorOptions(data);
        }
        // istanbul ignore next
      } catch (error) {
        console.log(error);
      }

      let payload = {};
      payload.host = selectedOption;

      // update DB through CAL to store host to filter on
      try {
        // eslint-disable-next-line
        const hostPayload = { host: selectedOption };
        const response = await fetch(
          `${apiEndpoint}/update_metrics_host_filter`,
          {
            mode: "cors",
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Access-Control-Allow-Origin": "*",
              accept: "application/json",
            },
            body: JSON.stringify(payload),
          }
        );
        // istanbul ignore next
        if (response.ok) {
          console.log(
            "Successfully sent selected host to backend: ",
            selectedOption
          );
        }
        // istanbul ignore next
      } catch (error) {
        console.log(error);
      }
    };

const Metrics = () => {
    const apiEndpoint = constants.Configs.api_endpoint;
    const [selectorOptions, setSelectorOptions] = useState([
      { value: "Host 1", label: "Host 1" },
      { value: "Host 2", label: "Host 2" },
    ]);
    // eslint-disable-next-line
    const [selectedOption, setSelectedOption] = useState(null);
    // istanbul ignore next
    const lastSelectedHost = useRef(() => {
      const savedValue = sessionStorage.getItem("lastSelectedHostValue");
      return savedValue ? savedValue : null;
    });
    
    const [dataAvailable, setDataAvailable] = useState(true);
    const hostCheckerInterval = useRef(null);
    const { memCapacityData, dramCxlMemUsageData, memoryCpuData, sendMessage } = useContext(WebSocketContext)
    const memCapacityOptions = {
      colors: ["#FFB546", "#0077C8", "#FE8E73", "#FEAE00", "B37328"],
      pieSliceText: 'value',
      backgroundColor: { fill:'transparent' },
      animation: {startup: true},
      is3D: true,
      label: 'GB',
      annotations: {
          textStyle: {
            fontName: 'Times-Roman',
            fontSize: 36,
            bold: true,
            italic: true,
            color: 'black',
            auraColor: '#FFFFFD',
            opacity: 0.8
          }
      },
      pieSliceTextStyle: {
          color: 'black',
          fontSize: 16,
          bold: true
      },
      legend: {textStyle: {color: '#FFFFFD', fontSize: 16}},
      chartArea: { width: "95%", height: "95%", top: 50, bottom: 40 },
  }
  const dramCxlMemUsageOptions = {
    isStacked: true,
    height: 220,
    colors: ["#0077C8", "#FFB546", "#00B3E3"],
    hAxis: {
      title: "Time",
      textStyle: { color: "#FFFFFD" },
      titleTextStyle: { color: "#FFFFFD" },
      gridlines: { color: "#8D8D8D", count: 0 },
    },
    vAxis: {
      title: "Memory Usage (%)",
      textStyle: { color: "#FFFFFD" },
      titleTextStyle: { color: "#FFFFFD" },
      viewWindow: { min: 0, max: 100 },
      gridlines: { color: "#8D8D8D", count: 0 },
    },
    curveType: "function",
    lineWidth: 5,
    legend: { position: "bottom", textStyle: { color: "#FFFFFD" } },
    chartArea: { width: "85%", height: "100%", top: 50, bottom: 50 },
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
  };

  const memoryCpuDatOptions = {
    curveType: "function",
    legend: { position: "bottom", textStyle: { color: "#FFFFFD" } },
    height: 480,
    lineWidth: 5,
    chartArea: { width: "85%", height: "100%", top: 50, bottom: 50 },
    colors: ["#0077C8", "#97D653", "#00B3E3"],
    backgroundColor: { fill: "transparent" },
    vAxis: {
      title: "Usage (%)",
      textStyle: { color: "#FFFFFD" },
      titleTextStyle: { color: "#FFFFFD" },
      viewWindow: { min: 0, max: 100 },
      gridlines: { color: "#8D8D8D", count: 0 },
    },
    hAxis: {
      textStyle: { color: "#FFFFFD" },
      titleTextStyle: { color: "#FFFFFD" },
      gridlines: { color: "4C4C3B" },
    },
    animation: { startup: true },
  };
  const ismemoryCpuDataValid =
  memoryCpuData !== null &&
  memoryCpuData !== "" &&
  !isNaN(Number(memoryCpuData)) &&
  (typeof memoryCpuData !== "object" ||
    Object.keys(memoryCpuData).length !== 0);

  const isCapacityDataValid = memCapacityData !== null &&
  memCapacityData !== "" &&
  !isNaN(Number(memCapacityData)) &&
  (typeof memCapacityData !== "object" ||
    Object.keys(memCapacityData).length !== 0);

  const isdramCxlMemUsageDataValid = dramCxlMemUsageData !== null &&
  dramCxlMemUsageData !== "" &&
  !isNaN(Number(dramCxlMemUsageData)) &&
  (typeof dramCxlMemUsageData !== "object" ||
    Object.keys(dramCxlMemUsageData).length !== 0)

  useEffect(() => {
    // istanbul ignore next
    const intervalCallBack = () => {
      if (lastSelectedHost.current) {
        let payload = {}
        payload.host = lastSelectedHost.current;
        sendMessage(payload);
      } else {
        console.log("last selected host is None");
      }
    };

    hostCheckerInterval.current = setInterval(intervalCallBack, 2000);

    return () => clearInterval(hostCheckerInterval.current);
  }, []);

  useEffect(() => {
    // Set timeout for 120 seconds (120000 ms)
    // istanbul ignore next
    const timer = setTimeout(() => {
      if (!ismemoryCpuDataValid || !isCapacityDataValid || !isdramCxlMemUsageDataValid ) {
        setDataAvailable(false);
      }
    }, 120000);

    // Clear timeout if data becomes available before the timeout elapses
    return () => clearTimeout(timer);
  }, [ismemoryCpuDataValid, isCapacityDataValid, isdramCxlMemUsageDataValid ]);
  return (
    <div className="Content content_root" id="main-container-id">
      <Container fluid>
        <Row>
          <Col>
            <div
              className="device_card memory-box-overview-height"
              data-testid="memory-box-overview"
              id="memory-box-overview-id"
            >
              <h4 className="metric-title">APPLICATION SERVER METRICS</h4>
            </div>
          </Col>
        </Row>
        <Row>
          <Col sm={6} md={6} lg={6}>
            <div
              className="device_card first-row"
              style={{ padding: 20, paddingTop: 50 }}
              id="app-server-card-id"
            >
              <Row>
                <Col sm={7} md={7} lg={7}>
                  <div className="fs-24 app-server-title">Select Server</div>{" "}
                </Col>
                <Col sm={5} md={5} lg={5}>
                  <div className="dropdownn-app-server">
                    <DropDown
                      options={selectorOptions}
                      onSelectChange={(selectedOption) =>
                        handleSelectChange(
                          selectedOption,
                          setSelectedOption,
                          setSelectorOptions,
                          sendMessage,
                          lastSelectedHost,
                          apiEndpoint
                        )
                      }
                    />
                  </div>
                </Col>
              </Row>
            </div>
          </Col>
          <Col sm={6} md={6} lg={6}>
            <Row>
              <Col sm={12} md={12} lg={12}>
                <div
                  className="device_card first-row"
                  id="memory-bandwidth-card-id"
                  data-testid="memory-bandwidth-card-id"
                >
                  <div className="bandwidth">
                    <Row>
                      <Col sm={4} md={4} lg={4} xl={4}>
                        <h1 className="fs-24 memory-bandwidth">
                          Memory{" "}
                          <span style={{ color: "white" }}>Bandwidth</span>
                        </h1>
                      </Col>
                      <Col sm={8} md={8} lg={8} xl={8}>
                        <div className="bandwidth-legend">
                          <span className="fs-22">CMM-D</span>
                        </div>
                        <div>
                          <div
                            className="progres-bar-label-metrics"
                            style={{ color: "white" }}
                          >
                            {`128 GBps`}
                          </div>
                          <ProgressBar now="50" key={2} className="host2" />
                          <div
                            className="progres-bar-title-metrics"
                            style={{ color: "white" }}
                          >{`Used Bandwidth 64 GBps`}</div>
                        </div>
                      </Col>
                    </Row>
                  </div>
                </div>
              </Col>
            </Row>
          </Col>
        </Row>
        <Row>
          <Col sm={7} md={7} lg={7} xl={7}>
            <div
              className="device_card second-row"
              id="saphaana-card-id"
              style={{ paddingBottom: 0, marginBottom: 0 }}
            >
              <div
                className="fs-22"
                style={{ display: "flex", alignItems: "baseline", height: 30 }}
              >
                <h1 className="sap-hana">CPU vs Memory Usage</h1>
              </div>
              {ismemoryCpuDataValid ? (
                <Chart
                  chartType="LineChart"
                  width="100%"
                  height="400px"
                  data={memoryCpuData}
                  options={memoryCpuDatOptions}
                />
              ) : dataAvailable ? (
                <div className="spinner-style" style={{ height: 400 }}>
                  <Spinner animation="border" variant="secondary" />
                </div>
              ) : (
                <div className="spinner-style" style={{ height: 400 }}>
                  <div style={{ color: "white", textAlign: "center", marginTop: 50 }}>
                      Data is not available
                  </div>
                </div>
              )}
            </div>
          </Col>
          <Col sm={5} md={5} lg={5} xl={5}>
            <Row>
              <Col>
                <div
                  className="device_card second-col-first-col"
                  id="mem-capacity-data-card-id"
                  data-testid="mem-capacity-data-card-id"
                >
                  <Row>
                    <Col sm={5} md={5} lg={5} xl={5}>
                      <div
                        className="fs-22"
                        style={{
                          display: "flex",
                          alignItems: "baseline",
                          height: 30,
                        }}
                      >
                        <h4 className="dram-cxl-title-pieChart">
                          Memory{" "}
                          <span style={{ color: "white" }}>Capacity (GiB)</span>
                        </h4>
                      </div>
                    </Col>
                    <Col sm={7} md={7} lg={7} xl={7}>
                      {isCapacityDataValid ? (
                        <Chart
                          chartType="PieChart"
                          data={memCapacityData}
                          options={memCapacityOptions}
                          width="100%"
                          height="250px"
                        />
                      ) : dataAvailable ? (
                        <div className="spinner-style" style={{ height: 250 }}>
                          <Spinner animation="border" variant="secondary" />
                        </div>
                      ) : (
                        <div className="spinner-style" style={{ height: 250 }}>
                          <div style={{ color: "white", textAlign: "center", marginTop: 50 }}>
                              Data is not available
                          </div>
                        </div>
                      )}
                    </Col>
                  </Row>
                </div>
              </Col>
            </Row>
            <Row>
              <Col>
                <div
                  className="device_card second-col-second-col"
                  id="dram-cxl-mem-data-card-id"
                  data-testid="dram-cxl-mem-data-card-id"
                >
                  <div
                    className="fs-22"
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      height: 30,
                    }}
                  >
                    <h4 className="memory-cpu-heading">
                      DRAM vs CXL Memory Usage
                    </h4>
                  </div>
                  {isdramCxlMemUsageDataValid ? (
                    <Chart
                      chartType="LineChart"
                      width="100%"
                      height="325px"
                      data={dramCxlMemUsageData}
                      options={dramCxlMemUsageOptions}
                    />
                  ) : dataAvailable ? (
                    <div className="spinner-style" style={{ height: 250 }}>
                      <Spinner animation="border" variant="secondary" />
                    </div>
                  ) : (
                    <div className="spinner-style" style={{ height: 250 }}>
                      <div style={{ color: "white", textAlign: "center" }}>
                          Data is not available
                      </div>
                    </div>
                  ) }
                </div>
              </Col>
            </Row>
          </Col>
        </Row>
      </Container>
    </div>
  );
};

export default Metrics;
