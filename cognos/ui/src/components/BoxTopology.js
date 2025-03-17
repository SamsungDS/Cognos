import React, { useEffect, useState } from "react";
import {
  Container,
  Row,
  Col,
  Badge,
  Carousel,
  Dropdown,
} from "react-bootstrap";
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
  fetchData,
  mergeHosts,
  updateHostListAttached,
} from "../constant";
import { ReactComponent as DeviceIcon } from "../assets/icons/deviceSVGIcon.svg";
import { useSelectedOption } from "../contexts/SelectedOptionContext";

const BoxTopology = () => {
  const [hostToDeviceMapping, setHostToDeviceMapping] = useState([]);
  // eslint-disable-next-line
  const [hostToDeviceMappingB2, setHostToDeviceMappingB2] = useState([]);
  const [currentCMM, setCurrentCMM] = useState(0);
  const [currentHostView, setCurrentHostView] = useState(0);
  const [hostList, setHostList] = useState([]);
  const [hostActiveList, setHostActiveList] = useState([]);

  const hostDeviceMapEndpoint = Configs.api_endpoint + "/topology";
  const hostMapEndpoint = Configs.api_endpoint + "/hosts";
  const { handleToggle, selectedOption } = useSelectedOption();
  const [isToggleEnabled, setIsToggleEnabled] = useState(false);
  const [selectedCluster, setSelectedCluster] = useState("None");
  const [clusterList, setClusterList] = useState([
    "None",
    "Cluster-A",
    "Cluster-B",
  ]);
  // Filtered data
  const [filteredDataHost, setFilteredDataHost] = useState(hostActiveList);
  const [filteredDataDevice, setFilteredDataDevice] =
    useState(hostToDeviceMapping);
  // Cluster mapping for hosts
  const hostClusterMapping = {
    "Host 1": "Cluster-A",
    "Host 2": "Cluster-A",
    "Host 3": "Cluster-B",
    "Host 4": "Cluster-B",
    "Host 5": "Cluster-A",
    "Host 6": "Cluster-B",
    "Host 7": "Cluster-A",
    "Host 8": "Cluster-B",
    "Host 9": "Cluster-A",
    "Host 10": "Cluster-B",
    "Host 11": "Cluster-A",
  };
  // Rules for determining clusters for unknown hosts
  // istanbul ignore next
  const determineClusterForUnknownHost = (hostValue) => {
    // Convert to lowercase for case-insensitive matching
    const hostLower = hostValue.toLowerCase();

    // Rule 1: Hosts starting with "msl-" go to Cluster-B
    if (hostLower.startsWith("msl-")) {
      return "Cluster-B";
    }

    // Rule 2: Hosts containing "host" go to Cluster-A
    if (hostLower.includes("host")) {
      return "Cluster-A";
    }

    // Default rule: Any other host gets null cluster
    return null;
  };

  useEffect(
    () => {
      fetchData(hostDeviceMapEndpoint, setHostToDeviceMapping);
      fetchData(hostMapEndpoint, setHostActiveList);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );
  useEffect(() => {
    // Function to add cluster information to hosts
    const addClusterToHosts = (hosts) => {
      return hosts.map((host) => {
        return {
          ...host,
          cluster: determineClusterForUnknownHost(host.value),
        };
      });
    };

    // Function to add cluster information to hosts
    const addClusterToDevice = (hosts) => {
      // istanbul ignore next
      return hosts.map((host) => {
        return {
          ...host,
          cluster: determineClusterForUnknownHost(host.host),
        };
      });
    };

    // Process the API response and update state
    const hostsWithClusters = addClusterToHosts(hostActiveList);
    const deviceWithClusters = addClusterToDevice(hostToDeviceMapping);
    setHostActiveList(hostsWithClusters);
    setHostToDeviceMapping(deviceWithClusters);
  }, []);
  // istanbul ignore next
  useEffect(
    () => {
      // Function to map hosts dynamically from a list
      const mapHosts = (hostNames) => {
        return hostNames.map((hostName) => {
          const { color } = defaultHostProperties[hostName] || {};
          const cluster = hostClusterMapping[hostName] || null;
          return {
            host: hostName,
            color,
            cluster,
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

  // Filter function to apply when selected cluster changes
  // istanbul ignore next
  useEffect(() => {
    if (selectedCluster === "None") {
      // Show all data when None is selected
      setFilteredDataDevice(hostToDeviceMapping);
      setFilteredDataHost(hostActiveList);
    } else {
      // Filter data based on selected cluster
      const filtered = hostToDeviceMapping.filter(
        (item) => item.cluster === selectedCluster
      );
      setFilteredDataDevice(filtered);

      const filteredHost = hostActiveList.filter(
        (host) => host.cluster === selectedCluster
      );
      setFilteredDataHost(filteredHost);
    }
  }, [selectedCluster]);
  // istanbul ignore next
  const filterByCluster = (clusterName) => {
    setSelectedCluster(clusterName);
  };

  const mappedDeviceViewList = (devices, type) => {
    // istanbul ignore next
    return devices.map((device) => ({
      dev_name: device,
      type: type,
    }));
  };

  const hostDirectView = updateHostListAttached(mergeHosts(filteredDataDevice));

  // istanbul ignore next
  const hostDirectViewList = hostDirectView.map((item) => ({
    title: item.host,
    deviceComponents: item.details.flatMap((detail) =>
      mappedDeviceViewList(detail.devices, detail.fm_type)
    ),
  }));

  useEffect(() => {
    if (hostDirectViewList.length > 0) {
      setIsToggleEnabled(true);
    } else {
      setIsToggleEnabled(false);
    }
  }, [hostDirectViewList]);

  const cmmList = [
    {
      title: "CMM-B1",
      hostComponents: mappedHostList(hostList, filteredDataHost),
      deviceComponents: mappedDeviceList(
        DeviceList,
        mappedHostList(hostList, filteredDataHost),
        filteredDataDevice
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
      hostComponents: mappedHostList(hostList, filteredDataHost),
      deviceComponents: mappedDeviceList(
        DeviceList,
        mappedHostList(hostList, filteredDataHost),
        filteredDataDevice
      ),
    },
    {
      title: "CMM-B4",
      hostComponents: mappedHostList(hostList, hostActiveList),
      deviceComponents: mappedDeviceList(
        DeviceList,
        hostList,
        hostToDeviceMappingB2
      ),
    },
    {
      title: "CMM-B5",
      hostComponents: mappedHostList(hostList, hostActiveList),
      deviceComponents: mappedDeviceList(
        DeviceList,
        hostList,
        hostToDeviceMappingB2
      ),
    },
    {
      title: "CMM-B6",
      hostComponents: mappedHostList(hostList, hostActiveList),
      deviceComponents: mappedDeviceList(
        DeviceList,
        hostList,
        hostToDeviceMappingB2
      ),
    },
  ];

  const renderHostComponents = (hosts) => {
    return hosts.map((host, index) => {
      const lineColor = host.color;
      // istanbul ignore next
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
      // istanbul ignore next
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
  // istanbul ignore next
  const renderHostViewDevice = (devices = []) => {
    return devices.map((device) => {
      const part = device.dev_name.split("-")[0];
      const deviceColor = "#FFB546";
      const D1Metadata = `name: ${part}
          type: ${device.type}
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
          <p
            className="device-Id"
            style={{ color: deviceColor }}
          >{`${part}`}</p>
        </div>
      );
    });
  };
  // Navigation handlers
  // istanbul ignore next
  const handlePrev = () => {
    setCurrentCMM((prevCMM) => (prevCMM === 0 ? 5 : prevCMM - 1));
  };
  // istanbul ignore next
  const handleNext = () => {
    setCurrentCMM((prevCMM) => (prevCMM === 5 ? 0 : prevCMM + 1));
  };
  // istanbul ignore next
  const handlePrevHostView = () => {
    setCurrentHostView((prevCMM) =>
      prevCMM === 0 ? hostDirectView.length - 1 : prevCMM - 1
    );
  };
  // istanbul ignore next
  const handleNextHostView = () => {
    setCurrentHostView((prevCMM) =>
      prevCMM === hostDirectView.length - 1 ? 0 : prevCMM + 1
    );
  };

  // istanbul ignore next
  return (
    <Container className="box-container" id="topology-card-id">
      <Row>
        <Col>
          <div className="cmm-navigation">
            {/* Add the cluster dropdown here */}
            <div className="cluster-dropdown-container">
              <Dropdown>
                <Dropdown.Toggle
                  variant="outline-secondary"
                  id="dropdown-cluster"
                >
                  Cluster: {selectedCluster}
                </Dropdown.Toggle>

                <Dropdown.Menu>
                  {clusterList.map((cluster, index) => (
                    <Dropdown.Item
                      key={index}
                      onClick={() => filterByCluster(cluster)}
                      active={selectedCluster === cluster}
                    >
                      {cluster}
                    </Dropdown.Item>
                  ))}
                </Dropdown.Menu>
              </Dropdown>
            </div>

            <div className="toggle-switch-container">
              <div className="toggle-switch">
                <input
                  type="checkbox"
                  id="switch"
                  className="toggle-input"
                  checked={selectedOption === "Host"}
                  onChange={handleToggle}
                  disabled={!isToggleEnabled}
                />
                <label
                  htmlFor="switch"
                  className={`toggle-label ${
                    isToggleEnabled ? "enabled" : "disabled"
                  }`}
                >
                  <span
                    className={`toggle-text left ${
                      selectedOption === "CMM-B" ? "visible" : "hidden"
                    }`}
                    // style={{ color: "#535353" }}
                  >
                    CMM-B
                  </span>
                  <span
                    className={`toggle-text right ${
                      selectedOption === "Host" ? "visible" : "hidden"
                    }`}
                  >
                    Host
                  </span>
                </label>
              </div>{" "}
            </div>
            {selectedOption === "CMM-B" ? (
              <>
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
                    className={`cmm-title ${
                      index === currentCMM ? "active" : ""
                    }`}
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
              </>
            ) : (
              <>
                <button
                  className="arrow-button left-arrow"
                  onClick={handlePrevHostView}
                >
                  <img src={ArrowLeft} alt="Previous" />
                </button>
                {hostDirectViewList.map((cmm, index) => (
                  <span
                    key={index}
                    className={`cmm-title ${
                      index === currentHostView ? "active" : ""
                    }`}
                    onClick={() => setCurrentHostView(index)}
                  >
                    {cmm.title}
                  </span>
                ))}
                <button
                  className="arrow-button right-arrow"
                  onClick={handleNextHostView}
                  disabled={hostDirectView.length - 1 === currentHostView}
                >
                  <img src={ArrowRight} alt="Next" />
                </button>
              </>
            )}
          </div>
          {selectedOption === "CMM-B" ? (
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
          ) : (
            <Carousel
              activeIndex={currentHostView}
              controls={false}
              indicators={false}
              interval={null}
            >
              {hostDirectViewList.map((cmm, index) => (
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
                        marginTop: 12,
                      }}
                    ></div>
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
                        {renderHostViewDevice(cmm.deviceComponents || [])}
                      </div>
                    </div>
                  </div>
                </Carousel.Item>
              ))}
            </Carousel>
          )}
        </Col>
      </Row>
    </Container>
  );
};

export default BoxTopology;
