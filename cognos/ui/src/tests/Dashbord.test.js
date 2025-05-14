import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Dashboard from '../pages/Dashboard';
import * as constants from '../constant';
import { SelectedOptionProvider } from "../contexts/SelectedOptionContext";


describe('Dashboard', () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  it('renders correctly', async () => {
    const mockVersion = { version: "2.0.1"}
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => (mockVersion),
    });

    const metricsData = { metric_type: 'cpu_mem_usage'};
    const fetchMetricsSpy = jest.spyOn(constants, 'fetchMetrics').mockResolvedValue(metricsData);

    render(
      <SelectedOptionProvider>
          <Dashboard />
      </SelectedOptionProvider>
    );
    expect(screen.getByTestId('box-topology-id')).toBeInTheDocument();
  });
});