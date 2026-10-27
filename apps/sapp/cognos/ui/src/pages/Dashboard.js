import React, { useState, useEffect, useRef } from "react";
import { Container, Row, Col } from "react-bootstrap";
import BoxTopology from "../components/BoxTopology";
import "./metrics.css";
import "./dashboard.css";
import "rc-slider/assets/index.css";
import * as constants from '../constant';
import { useSelectedOption } from "../contexts/SelectedOptionContext";
import { VIEW_MODES, DeviceCountCard, CapacityCard, BandwidthCard, MemoryUsageChart } from '../utils/dashboard-utils';

const POLL_INTERVAL = 3000;

// Enable/disable mock mode for testing
const MOCK_MODE = false;

const MOCK_DATA = {
  version: { version: "01.02.03" },
  cluster_metrics: {
    memory_usage: [
      ["Time", "DRAM", "CXL"],
      ["5", 151, 142],
      ["4", 481, 211],
      ["3", 831, 418],
      ["2", 996, 642],
      ["1", 1030, 795],
      ["Current", 120, 400]
    ],
    capacity: {
      total_capacity: 5057,
      used_capacity: 0,
      used_capacity_percentage: 0
    },
    bandwidth: {
      max_bandwidth: 64,
      used_bandwidth: 32,
      used_percentage_bandwidth: 50
    },
    devices_count: {
      num_hosts: 1,
      num_cxl_devices: 2
    }
  },
  cmmb_usage: [
    ["Time", "Usage"],
    ["10:00", 3200],
    ["10:05", 3500],
    ["10:10", 3800],
    ["10:15", 4100],
    ["10:20", 4400]
  ],
  cmmb_capacity: {
    total_capacity: 256,
    used_capacity: 128,
    used_capacity_percentage: 50
  },
  cmmb_bandwidth: {
    max_bandwidth: 32,
    used_bandwidth: 16,
    used_percentage_bandwidth: 50
  },
  devices_count: {
    num_hosts: 4,
    num_cxl_devices: 12
  },
  memserver_capacity: [
    ["Memtype", "Capacity Used"],
    ["DRAM", 1031],
    ["CXL", 4026],
  ]
};
// istanbul ignore next
const mockFetch = (url, options) => {
  return new Promise((resolve) => {
    setTimeout(() => {

      if (url.includes('/scmc_version')) {
        resolve({
          ok: true,
          json: async () => MOCK_DATA.version
        });
      } else if (url.includes('/cluster_metrics')) {
        resolve({
          ok: true,
          json: async () => MOCK_DATA.cluster_metrics
        });
      } else if (url.includes('/metrics')) {
        const payload = options?.body ? JSON.parse(options.body) : {};
        const metricType = payload.metric_type;

        const mockResponse = MOCK_DATA[metricType] || {};
        resolve({
          ok: true,
          json: async () => mockResponse
        });
      }
    }, 500); // Simulate network delay
  });
};

/**
 * Custom hook for polling metrics data
 * @param {string} metricType - The type of metric to fetch
 * @param {object} additionalPayload - Additional payload parameters
 * @param {number} interval - Polling interval in milliseconds
 */
// istanbul ignore next
const useMetricsPoll = (clusterRef, metricType, additionalPayload = {}, interval = POLL_INTERVAL) => {
  const [data, setData] = useState([]);
  const dataRef = useRef({});
  const apiEndpoint = MOCK_MODE ? '' : constants.Configs.api_endpoint;

  useEffect(() => {
    const fetchData = async () => {
      try {
        const payload = {
          cluster: clusterRef.current,
          metric_type: metricType,
          ...additionalPayload
        };

        let response;
        if (MOCK_MODE) {
          response = await mockFetch(`${apiEndpoint}/metrics`, {
            method: 'POST',
            body: JSON.stringify(payload)
          });
        } else {
          response = await constants.fetchMetrics(
            `${apiEndpoint}/metrics`,
            payload
          );
        }

        if (response?.ok) {
          const result = await response.json();
          dataRef.current = result;
          setData(result);
        } else {
          console.error(`Unable to fetch ${metricType} data`);
        }
      } catch (error) {
        console.error(`Error fetching ${metricType}:`, error);
      }
    };

    fetchData();
    const intervalId = setInterval(fetchData, interval);

    return () => clearInterval(intervalId);
  }, [metricType, interval, apiEndpoint, JSON.stringify(additionalPayload)]);

  return data;
};

const Dashboard = () => {
  const { selectedOption } = useSelectedOption();
  const [version, setVersion] = useState('00.00.00');
  const [viewMode, setViewMode] = useState(VIEW_MODES.HOST); // Default to host view
  const apiEndpoint = MOCK_MODE ? '' : constants.Configs.api_endpoint;
  const [metricsCluster, setMetricsCluster] = useState("None");
  const metricsClusterRef = useRef(metricsCluster);

  // check selected cluster
  useEffect(() => {
    console.log("DASHBOARD SELECTED CLUSTER: ", metricsCluster);
    metricsClusterRef.current = metricsCluster;
  }, [metricsCluster]);

  // Fetch version
  useEffect(() => {
    const getVersion = async () => {
      try {
        let response;
        if (MOCK_MODE) {
          response = await mockFetch(`${apiEndpoint}/scmc_version`, {
            mode: 'cors',
            method: 'GET',
          });
        } else {
          response = await fetch(`${apiEndpoint}/scmc_version`, {
            mode: 'cors',
            method: 'GET',
            headers: {
              'Content-Type': 'application/json',
              'accept': 'application/json',
              'Access-Control-Allow-Origin': '*'
            },
          });
        }

        if (response.ok) {
          const data = await response.json();
          setVersion(data);
        } else {
          console.log("unable to fetch version number");
        }
      } catch (error) {
        console.error("Error fetching version:", error);
      }
    };
    getVersion();
  }, [apiEndpoint]);

  // Update view mode based on selectedOption
  useEffect(() => {
    const newViewMode = selectedOption === VIEW_MODES.CMMB ? VIEW_MODES.CMMB : VIEW_MODES.HOST;
    setViewMode(newViewMode);
  }, [selectedOption]);

  // Fetch metrics using custom hooks
  const cmmbMemoryData = useMetricsPoll(metricsClusterRef, "cmmb_usage");
  const cmmbCapacityData = useMetricsPoll(metricsClusterRef, "cmmb_capacity");
  const cmmbBandwidthData = useMetricsPoll(metricsClusterRef, "cmmb_bandwidth")
  const devicesCountData = useMetricsPoll(metricsClusterRef, "devices_count");

  // Fetch cluster metrics for host view
  // const clusterMetrics = useClusterMetrics(viewMode);
  const clusterMetrics = {
    "memory_usage": useMetricsPoll(metricsClusterRef, "hostview_usage"),
    "capacity": useMetricsPoll(metricsClusterRef, "hostview_capacity"),
    "bandwidth": useMetricsPoll(metricsClusterRef, "hostview_bandwidth"),
    "devices_count": devicesCountData
  }

  // Determine data source based on view mode
  const displayData = viewMode === VIEW_MODES.HOST && clusterMetrics
    ? {
        memory: clusterMetrics.memory_usage || cmmbMemoryData,
        capacity: clusterMetrics.capacity || cmmbCapacityData,
        bandwidth: clusterMetrics.bandwidth || cmmbBandwidthData,
        devices: clusterMetrics.devices_count || devicesCountData
      }
    : {
        memory: cmmbMemoryData,
        capacity: cmmbCapacityData,
        bandwidth: cmmbBandwidthData,
        devices: devicesCountData
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
              <h4 className="memory-box-title">
                Dashboard - {viewMode === VIEW_MODES.HOST ? 'Host View' : 'CMM-B View'}
              </h4>
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
              <BoxTopology onClusterChange={setMetricsCluster} />
            </div>
          </Col>

          <Col sm={12} md={12} lg={12} xl={4}>
            <DeviceCountCard
              hostsCount={displayData.devices.num_hosts}
              devicesCount={displayData.devices.num_cxl_devices}
              isLoading={!displayData.devices.num_hosts}
            />

            <Row>
              <Col>
                <CapacityCard
                  viewMode={viewMode}
                  capacityData={displayData?.capacity?.hostview_capacity}
                  memCapacityData={displayData?.capacity?.hostview_memserver_capacity}
                  isLoading={!displayData?.capacity?.hostview_capacity}
                />
              </Col>
            </Row>
          </Col>
        </Row>

        <Row>
          <Col sm={12} md={12} lg={12} xl={8}>
            <MemoryUsageChart
              viewMode={viewMode}
              memoryData={displayData.memory}
              isLoading={!displayData.memory || displayData.memory.length <= 1}
            />
          </Col>

          <Col sm={12} md={12} lg={12} xl={4}>
            <BandwidthCard
              viewMode={viewMode}
              bandwidthData={displayData.bandwidth}
              isLoading={!displayData.bandwidth.max_bandwidth}
            />
          </Col>
        </Row>

        <Row>
          <Col>
            <div className="device_card memory-box-overview-height text-center">
              <h4 className="memory-box-title1">
                Samsung Cognos Management Console ({version.version})
              </h4>
            </div>
          </Col>
        </Row>
      </Container>
    </div>
  );
};

export default Dashboard;