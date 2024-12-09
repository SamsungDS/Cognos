import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Dashboard from '../pages/Dashboard';
import * as constants from '../constant';
import WebSocketContext from '../contexts/WebSocketContext';
import { SelectedOptionProvider } from "../contexts/SelectedOptionContext";


describe('Dashboard', () => {
    test('renders correctly', () => {

      const devicesCountData = {
        'num_hosts': 3
      };
  
      const cmmbCapacityData = {
        'total_capacity': 10000,
        'used_capacity': 5000
      }
  
      const cmmbBandwidthData = {
        'max_bandwidth': 32
      }

      const cmmbMemoryData = {
        'total_memory': 64
      }

      render(
        <WebSocketContext.Provider value={{ cmmbMemoryData, cmmbCapacityData, cmmbBandwidthData, devicesCountData }}>
          <SelectedOptionProvider>
              <Dashboard />
          </SelectedOptionProvider>
        </WebSocketContext.Provider>
      );
      expect(screen.getByTestId('box-topology-id')).toBeInTheDocument();
    });
  });