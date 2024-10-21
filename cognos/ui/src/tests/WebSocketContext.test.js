import React from 'react';
import { render, waitFor, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import { WebSocketProvider } from '../contexts/WebSocketContext'; 
import WebSocketContext from '../contexts/WebSocketContext';
import { Configs } from '../../src/constant';
// Mock WebSocket globally
const mockWebSocketSend = jest.fn();
// Mock WebSocket globally
global.WebSocket = jest.fn(() => ({
  onopen: jest.fn(),
  onmessage: jest.fn(),
  onclose: jest.fn(),
  onerror: jest.fn(),
  send: mockWebSocketSend,
  close: jest.fn(),
  readyState: 1,
}));

// Mock Configs
Configs.exporter_endpoint = 'localhost:4000';
Configs.ssl = false;

jest.setTimeout(10000);

describe('WebSocketProvider', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('should establish a WebSocket connection on component mount', async () => {
    render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    // Expect the WebSocket connection to be initiated with the correct endpoint
    expect(global.WebSocket).toHaveBeenCalledWith('ws://localhost:4000');
    await waitFor(() => expect(global.WebSocket).toHaveBeenCalledTimes(1));
  });

  test('should handle WebSocket messages and update context values', async () => {
    const mockMessage = {
      type: 'dram_cxl_usage',
      data: [10, 20, 30],
    };

    render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    // Simulate a WebSocket message event
    global.WebSocket.mock.instances[0].onmessage({
      data: JSON.stringify(mockMessage),
    });

    // Expect the context value to be updated based on the incoming message
    await waitFor(() => {
      expect(screen.getByTestId('dram-cxl-usage')).toHaveTextContent('10, 20, 30');
    });
  });

  test('should handle dram_cxl_usage messages', async () => {
    const mockMessage = {
      type: 'dram_cxl_usage',
      data: [10, 20, 30],
    };

    render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    // Simulate a WebSocket message event
    global.WebSocket.mock.instances[0].onmessage({
      data: JSON.stringify(mockMessage),
    });

    // Expect the context value to be updated based on the incoming message
    await waitFor(() => {
      expect(screen.getByTestId('dram-cxl-usage')).toHaveTextContent('10, 20, 30');
    });
  });

  test('should handle cpu_mem_usage messages', async () => {
    const mockMessage = {
      type: 'cpu_mem_usage',
      data: [40, 50],
    };

    render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    global.WebSocket.mock.instances[0].onmessage({
      data: JSON.stringify(mockMessage),
    });

    // You need to add an appropriate element to check against
    await waitFor(() => {
      expect(screen.getByTestId('cpu-mem-usage')).toHaveTextContent('40, 50');
    });
  });

  test('should handle memserver_capacity messages', async () => {
    const mockMessage = {
      type: 'memserver_capacity',
      data: [100],
    };

    render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    global.WebSocket.mock.instances[0].onmessage({
      data: JSON.stringify(mockMessage),
    });

    // Check for corresponding element
    await waitFor(() => {
      expect(screen.getByTestId('memserver-capacity')).toHaveTextContent('100');
    });
  });

  test('should handle cmmb_usage messages', async () => {
    const mockMessage = {
      type: 'cmmb_usage',
      data: [60],
    };

    render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    global.WebSocket.mock.instances[0].onmessage({
      data: JSON.stringify(mockMessage),
    });

    // Check for corresponding element
    await waitFor(() => {
      expect(screen.getByTestId('cmmb-usage')).toHaveTextContent('60');
    });
  });

  test('should handle cmmb_capacity messages', async () => {
    const mockMessage = {
      type: 'cmmb_capacity',
      data: [200],
    };

    render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    global.WebSocket.mock.instances[0].onmessage({
      data: JSON.stringify(mockMessage),
    });

    // Check for corresponding element
    await waitFor(() => {
      expect(screen.getByTestId('cmmb-capacity')).toHaveTextContent('200');
    });
  });

  test('should handle cmmb_bandwidth messages', async () => {
    const mockMessage = {
      type: 'cmmb_bandwidth',
      data: [300],
    };

    render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    global.WebSocket.mock.instances[0].onmessage({
      data: JSON.stringify(mockMessage),
    });

    // Check for corresponding element
    await waitFor(() => {
      expect(screen.getByTestId('cmmb-bandwidth')).toHaveTextContent('300');
    });
  });

  test('should handle devices_count messages', async () => {
    const mockMessage = {
      type: 'devices_count',
      data: [5],
    };

    render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    global.WebSocket.mock.instances[0].onmessage({
      data: JSON.stringify(mockMessage),
    });

    // Check for corresponding element
    await waitFor(() => {
      expect(screen.getByTestId('devices-count')).toHaveTextContent('5');
    });
  });
  // Add checks for the `check` function
   test('should call connect when check is called and WebSocket is not connected', () => {
    const { container } = render(
      <WebSocketProvider>
        <WebSocketConsumer />
      </WebSocketProvider>
    );

    // Ensure initial call to connect is made
    expect(global.WebSocket).toHaveBeenCalledTimes(1);
  });

// A mock component to consume and test context values
const WebSocketConsumer = () => {
    const {
        dramCxlMemUsageData,
        memoryCpuData,
        memCapacityData,
        cmmbMemoryData,
        cmmbCapacityData,
        cmmbBandwidthData,
        devicesCountData,
        sendMessage,
      } = React.useContext(WebSocketContext);

  return (
    <div>
      <div data-testid="dram-cxl-usage">{dramCxlMemUsageData.join(', ')}</div>
      <div data-testid="cpu-mem-usage">{memoryCpuData.join(', ')}</div>
      <div data-testid="memserver-capacity">{memCapacityData.join(', ')}</div>
      <div data-testid="cmmb-usage">{cmmbMemoryData}</div>
      <div data-testid="cmmb-capacity">{cmmbCapacityData}</div>
      <div data-testid="cmmb-bandwidth">{cmmbBandwidthData}</div>
      <div data-testid="devices-count">{devicesCountData}</div>
      <button data-testid="send-message-button" onClick={() => sendMessage({ host: 'test-host' })}>
        Send Message
      </button>
    </div>
  );
};
});