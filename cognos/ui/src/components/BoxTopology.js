import React, { useEffect, useState } from "react";
import { Container, Row, Col, Badge, Carousel } from "react-bootstrap";
import "rc-slider/assets/index.css";
import "./BoxTopology.css";
import {
  Configs,
  ArrowLeft,
  ArrowRight,
  DeviceList,
  DeviceList1,
  defaultHostProperties,
  mappedHostList,
  mappedDeviceList,
  fetchData
} from "../constant";
import { ReactComponent as DeviceIcon } from "../assets/icons/deviceSVGIcon.svg";

const BoxTopology = () => {
  const [hostToDeviceMapping, setHostToDeviceMapping] = useState([]);
  // eslint-disable-next-line
  const [hostToDeviceMappingB2, setHostToDeviceMappingB2] = useState([]);
  const [currentCMM, setCurrentCMM] = useState(0);
  const [hostList, setHostList] = useState([]);
  const [hostActiveList, setHostActiveList] = useState([]);
  const hostDeviceMapEndpoint = Configs.api_endpoint + "/topology";
  const hostMapEndpoint = Configs.api_endpoint + "/hosts";
  
  useEffect(
    () => {
      fetchData(hostDeviceMapEndpoint, setHostToDeviceMapping);
      fetchData(hostMapEndpoint, setHostActiveList);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );
  console.log(hostToDeviceMapping);

  console.log(hostActiveList);

  useEffect(
    () => {
      // Function to map hosts dynamically from a list
      const mapHosts = (hostNames) => {
        return hostNames.map((hostName) => {
          const { color } = defaultHostProperties[hostName] || {};
          return {
            host: hostName,
            color,
          };
        });
      };
      // Map HostList dynamically
      const hostsFromConfig = mapHosts(Configs.HostList);
      setHostList(hostsFromConfig);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const cmmList = [
    {
      title: "CMM-B1",
      hostComponents: mappedHostList(hostList, hostActiveList),
      deviceComponents: mappedDeviceList(
        DeviceList,
        mappedHostList(hostList, hostActiveList),
        hostToDeviceMapping
      ),
    },
    {
      title: "CMM-B2",
      hostComponents: mappedHostList(hostList, hostToDeviceMappingB2),
      deviceComponents: mappedDeviceList(
        DeviceList1,
        hostList,
        hostToDeviceMappingB2
      ),
    },
    {
      title: "CMM-B3",
      hostComponents: mappedHostList(hostList, hostToDeviceMapping),
      deviceComponents: mappedDeviceList(
        DeviceList,
        hostList,
        hostToDeviceMapping
      ),
    },
    {
      title: "CMM-B4",
      hostComponents: mappedHostList(hostList, hostToDeviceMapping),
      deviceComponents: mappedDeviceList(
        DeviceList,
        hostList,
        hostToDeviceMapping
      ),
    },
    {
      title: "CMM-B5",
      hostComponents: mappedHostList(hostList, hostToDeviceMapping),
      deviceComponents: mappedDeviceList(
        DeviceList,
        hostList,
        hostToDeviceMapping
      ),
    },
    {
      title: "CMM-B6",
      hostComponents: mappedHostList(hostList, hostToDeviceMapping),
      deviceComponents: mappedDeviceList(
        DeviceList,
        hostList,
        hostToDeviceMapping
      ),
    },
  ];

  const renderHostComponents = (hosts) => {
    return hosts.map((host, index) => {
      const lineColor = host.color;
      const dynamicStyle = {
        color: host.isActive ? host.color : "#4F4F4F",
        border: host.isActive ? `2px solid ${host.color}` : "2px solid #4F4F4F",
      };

      const Metadata = `name: ${host.host},
          port: 3,
          port_type: CXL_11,
          PCIe_version: 5,
          PCIe_lanes: 8,
          `.replace(/ +/g, "");
      const lineStyle = {
        background: host.isActive ? "white" : "#4F4F4F",
        marginBottom: "8px",
      };
      return (
        <div key={host.host}>
          <div>
            <Badge
              className="badge"
              style={{
                ...dynamicStyle,
                maxWidth: "100px",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
              title={Metadata}
            >
              <span
                className="vertical-badge-line"
                style={{ color: lineColor, fontWeight: 900 }}
              >
                | | |{" "}
              </span>
              <span
                className="badge-name"
                style={{ paddingTop: 4, fontFamily: "samsung sharp sons" }}
              >
                &nbsp; {`${host.host}`}
              </span>
            </Badge>
            <div>
              <div className="vertical-line" style={lineStyle}></div>
            </div>
          </div>
        </div>
      );
    });
  };

  const renderDeviceComponents = (devices) => {
    return devices.map((device) => {
      const part = device.device.split("-")[0];
      const deviceColor = device.color;
      const D1Metadata = `name: ${part}
          size: 256GB
          port: 7
          dev_port_type: CXL_20
          PCIe_version: 5
          PCIe_lanes: 8
          `.replace(/ +/g, "");
      const deviceCount = devices.length;
      const sizeMultiplier = deviceCount > 8 ? 1 : 1.3;
      const sizePadding = deviceCount > 8 ? "0" : "0rem 1rem 0rem 1rem";
      const cardStyle = {
        transform: `scale(${sizeMultiplier})`,
        padding: sizePadding,
      };

      return (
        <div
          className="cxl-dev"
          title={D1Metadata}
          key={device.device}
          style={cardStyle}
        >
          <DeviceIcon style={{ color: deviceColor }} className="device-img" />
          <p className="fs-22 device-Id">{`${part}`}</p>
        </div>
      );
    });
  };
  // Navigation handlers
  const handlePrev = () => {
    setCurrentCMM((prevCMM) => (prevCMM === 0 ? 5 : prevCMM - 1));
  };

  const handleNext = () => {
    setCurrentCMM((prevCMM) => (prevCMM === 5 ? 0 : prevCMM + 1));
  };

  return (
    <Container className="box-container" id="topology-card-id">
      <Row>
        <Col>
          <div className="cmm-navigation">
            <button
              className="arrow-button left-arrow"
              onClick={handlePrev}
              data-testid="prev-button"
            >
              <img src={ArrowLeft} alt="Previous" />
            </button>
            {cmmList.map((cmm, index) => (
              <span
                key={index}
                className={`cmm-title ${index === currentCMM ? "active" : ""}`}
                data-testid="specific-button"
                onClick={() => setCurrentCMM(index)}
              >
                {cmm.title}
              </span>
            ))}
            <button
              className="arrow-button right-arrow"
              data-testid="next-button"
              onClick={handleNext}
            >
              <img src={ArrowRight} alt="Next" />
            </button>
          </div>
          <Carousel
            activeIndex={currentCMM}
            controls={false}
            indicators={false}
            interval={null}
          >
            {cmmList.map((cmm, index) => (
              <Carousel.Item key={index}>
                <div className="carousel-content">
                  <div
                    className="badge-container"
                    id="host-card-id"
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                      textAlign: "center",
                    }}
                  >
                    {renderHostComponents(cmm.hostComponents)}
                  </div>
                  <div
                    className="device-box"
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                    }}
                    id="cxl-device-card-id"
                  >
                    <div
                      className="cxl-device"
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        fontFamily: "Samsung",
                        textAlign: "center",
                        justifyContent: "space-around",
                      }}
                    >
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
  );
};

export default BoxTopology;