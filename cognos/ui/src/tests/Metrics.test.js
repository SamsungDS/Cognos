import React, { useRef, useState } from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Metrics from '../pages/Metrics';
import {handleSelectChange, checkSelectedHost} from '../pages/Metrics';
import * as constants from '../constant';


describe('Metric component', () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  it('tests for fetching metrics data successfully', async () => {
    const mockOptions = ([
      { value: "Host 1", label: "Host 1" },
      { value: "Host 2", label: "Host 2" },
    ]);
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => (mockOptions),
    });

    const metricsData = { metric_type: 'cpu_mem_usage'};
    const fetchMetricsSpy = jest.spyOn(constants, 'fetchMetrics').mockResolvedValue(metricsData);

    render(
      <Metrics />
    );
  });

  // it('failed metrics calls', () => {
  //   const mockOptions = ([
  //     { value: "Host 1", label: "Host 1" },
  //     { value: "Host 2", label: "Host 2" },
  //   ]);
  //   fetch.mockResolvedValueOnce({
  //     ok: true,
  //     json: async () => (mockOptions),
  //   });

  //   const metricsData = { metric_type: 'cpu_mem_usage'};
  //   const fetchMetricsSpy = jest.spyOn(constants, 'fetchMetrics').mockRejectedValue(new Error("Failed to fetch metrics data"));

  //   render(
  //     <Metrics />
  //   );
  // })

  // it('renders memCapacityData chart correctly', () => {
  //   const setSelectorOptions = jest.fn();
  //   jest.spyOn(React, 'useState').mockImplementation(init => [init, setSelectorOptions]);
  //   const memCapacityData = jest.fn()
  //   const dramCxlMemUsageData = jest.fn()
  //   const memoryCpuData = jest.fn()
  //   render(
  //     <Metrics />
  //   );
  // });

  // it('renders dramCxlMemUsageData chart correctly', () => {
  //   const setSelectorOptions = jest.fn();
  //   jest.spyOn(React, 'useState').mockImplementation(init => [init, setSelectorOptions]);
  //   const memCapacityData = jest.fn()
  //   const dramCxlMemUsageData = jest.fn()
  //   const memoryCpuData = jest.fn()
  //   render(
  //     <Metrics />
  //   );
  // });

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

    const mockOptions = ([
      { value: "Host 1", label: "Host 1" },
      { value: "Host 2", label: "Host 2" },
    ]);
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => (mockOptions),
    });

    const metricsData = { metric_type: 'cpu_mem_usage'};
    const fetchMetricsSpy = jest.spyOn(constants, 'fetchMetrics').mockResolvedValue(metricsData);

    render(
      <Metrics />
    );

    global.fetch = jest.fn();
    const endpoint = 'test_endpt'
    const mockResponse = ['xxx'];
    const mockFetch = Promise.resolve({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    global.fetch.mockImplementation(() => mockFetch);
    const mockSelectedOption = 'test_host';
    const mockSetSelectedOption = jest.fn();

    const mockSelectorOptionsRef = { current: ['host1','host2'] };
    const mockSetSelectorOptions = jest.fn();
    const mockSendMessage = jest.fn();
    const mockLastSelectedHost = { current: "test_host2"};
    const mockApiEndpoint = "/api/v2.0.1";

    const result = await handleSelectChange(
      mockSelectedOption,
      mockSetSelectedOption,
      mockSelectorOptionsRef,
      mockSetSelectorOptions,
      mockSendMessage,
      mockLastSelectedHost,
      mockApiEndpoint
    );
  });


});
