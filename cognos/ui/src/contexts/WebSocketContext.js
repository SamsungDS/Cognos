import React, { createContext, useState, useEffect, useRef } from 'react';
import { Configs } from '../constant';

const WebSocketContext = createContext(null);

export const WebSocketProvider = ({ children }) => {
  const [cmmbMemoryData, setCMMBMemoryData] = useState(null);
  const [dramCxlMemUsageData, setDramCxlMemUsageData] = useState([]);
  const [memoryCpuData, setMemoryCpuData] = useState([]);
  const [memCapacityData, setMemCapacityData] = useState([]);
  const [cmmbCapacityData, setCmmbCapacityData] = useState([]);
  const [cmmbBandwidthData, setCmmbBandwidthData] = useState([]);
  const [devicesCountData, setDevicesCountData] = useState([]);
  const ws = useRef(null);

  useEffect(() => {
    ws.current = new WebSocket(`ws://${Configs.exporter_endpoint}`);

    ws.current.onopen = () => {
      console.log("UI opened connection to websocket");
    };

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case "dram_cxl_usage":
            setDramCxlMemUsageData(data.data)
            break;
        case "cpu_mem_usage":
            setMemoryCpuData(data.data)
            break;
        case "memserver_capacity":
            setMemCapacityData(data.data)
            break;
        case "cmmb_usage":
            setCMMBMemoryData(data.data)
            break;
        case "cmmb_capacity":
            setCmmbCapacityData(data.data)
            break;
        case "cmmb_bandwidth":
          setCmmbBandwidthData(data.data)
          break;
        case "devices_count":
          setDevicesCountData(data.data)
          break;
        default:
            break;
      }
    };

    ws.current.onclose = () => {
      console.log("UI closed connection to websocket");
    };

    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, []);

  const sendMessage = (message) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    } else {
      console.error('WebSocket is not open'+ JSON.stringify(message.host));
    }
  };

  return (
    <WebSocketContext.Provider value={{ cmmbMemoryData, dramCxlMemUsageData, memoryCpuData, memCapacityData, cmmbCapacityData, cmmbBandwidthData, devicesCountData, sendMessage }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export default WebSocketContext;