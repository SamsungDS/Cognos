import React, { useRef } from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Metrics from '../pages/Metrics';
import {handleSelectChange, checkSelectedHost} from '../pages/Metrics';
import WebSocketContext from '../contexts/WebSocketContext';


describe('Metric component', () => {
  it('renders memCapacityData chart correctly', () => {
    const memCapacityData = jest.fn()
    const dramCxlMemUsageData = jest.fn()
    const memoryCpuData = jest.fn()
    const { getByTestId } = render(
      <WebSocketContext.Provider value={{ dramCxlMemUsageData, memoryCpuData, memCapacityData }}>
        <Metrics />
      </WebSocketContext.Provider>
    );
    const memCapacityChart = getByTestId('mem-capacity-data-card-id');
    expect(memCapacityChart).toBeInTheDocument();
  });

  it('renders dramCxlMemUsageData chart correctly', () => {
    const memCapacityData = jest.fn()
    const dramCxlMemUsageData = jest.fn()
    const memoryCpuData = jest.fn()
    const { getByTestId } = render(
      <WebSocketContext.Provider value={{ dramCxlMemUsageData, memoryCpuData, memCapacityData }}>
        <Metrics />
      </WebSocketContext.Provider>
    );
    const dramCxlMemChart = getByTestId('dram-cxl-mem-data-card-id');
    expect(dramCxlMemChart).toBeInTheDocument();
  });

  it('test host selection', async () => {
    jest.mock('react', () => ({
      ...jest.requireActual('react'),
      useState: jest.fn(),
    }));
    const setMockVar = jest.fn();
    jest.spyOn(React, 'useState').mockImplementation((init) => [init, setMockVar]);

    const memCapacityData = jest.fn()
    const dramCxlMemUsageData = jest.fn()
    const memoryCpuData = jest.fn()
    const { getByTestId } = render(
      <WebSocketContext.Provider value={{ dramCxlMemUsageData, memoryCpuData, memCapacityData }}>
        <Metrics />
      </WebSocketContext.Provider>
    );

    global.fetch = jest.fn();
    const endpoint = 'test_endpt'
    const mockResponse = { data: 'xxx' };
    const mockFetch = Promise.resolve({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    global.fetch.mockImplementation(() => mockFetch);
    const mockSelectedOption = 'test_host';
    const mockSetSelectedOption = jest.fn();
    const mockSetSelectorOptions = jest.fn();
    const mockSendMessage = jest.fn();
    const mockLastSelectedHost = { current: "test_host2"};
    const mockApiEndpoint = "/api/v2.0.1";
    const result = await handleSelectChange(
      mockSelectedOption,
      mockSetSelectedOption,
      mockSetSelectorOptions,
      mockSendMessage,
      mockLastSelectedHost,
      mockApiEndpoint
    );
  });


});
