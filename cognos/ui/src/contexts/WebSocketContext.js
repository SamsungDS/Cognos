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

  function connect() {
    console.log("TRYING TO CONNECT TO: ", Configs.exporter_endpoint);

    if (Configs.ssl) {
        ws.current = new WebSocket(`wss://${Configs.exporter_endpoint}`);
    } else {
        ws.current = new WebSocket(`ws://${Configs.exporter_endpoint}`);
    }
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

    ws.current.onclose = (event) => {
      if (event.wasClean) {
        console.log("Clean termination to websocket");
      } else {
        console.log("Closing websocket");
        console.error("Unexpected termination of websocket");
        ws.current.close();
        ws.current = null;
      }
    };

    ws.current.onerror = (err) => {
      console.error('websocket error: ', err);
    };
  }

  function check() {
    if(!ws) {
      connect();
    } else if (!ws.current) {
        connect();
    } else if (ws.current.readyState === 3) {
        connect();
    }
  }


  useEffect(() => {
    connect();
    setInterval(check, 5000);
  }, []);

  const sendMessage = (message) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      console.log('SENDING MSG TO EXPORTER: ', message);
      try {
        ws.current.send(JSON.stringify(message));
      } catch (err) {
          console.error('Error sending message: ', err);
      }
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
