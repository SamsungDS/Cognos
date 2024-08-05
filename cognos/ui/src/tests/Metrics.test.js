import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import   Metrics from '../pages/Metrics';
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

});
