import React from 'react';
import { render} from '@testing-library/react';
import App from './App';
import WebSocketContext from './contexts/WebSocketContext';
import { SelectedOptionProvider } from './contexts/SelectedOptionContext';

describe('App', () => {
  test('renders without crashing', () => {

    const devicesCountData = {
      'num_hosts': 1
    };

    const cmmbCapacityData = {
      'total_capacity': 50
    }

    const cmmbBandwidthData = {
      'max_bandwidth': 100
    }

    render(
      <WebSocketContext.Provider value={{devicesCountData, cmmbCapacityData, cmmbBandwidthData}}>
        <SelectedOptionProvider>
          <App />
        </SelectedOptionProvider>
      </WebSocketContext.Provider>
    );
  });

  test('renders header', () => {

    const devicesCountData = {
      'num_hosts': 5
    };

    const cmmbCapacityData = {
      'total_capacity': 500
    }

    const cmmbBandwidthData = {
      'max_bandwidth': 64
    }

    const { getByText } = render(
      <WebSocketContext.Provider value={{devicesCountData, cmmbCapacityData, cmmbBandwidthData}}>
        <SelectedOptionProvider>
          <App />
        </SelectedOptionProvider>
      </WebSocketContext.Provider>
    );
    expect(getByText(/Cognos Management Console/i)).toBeInTheDocument();
  });

  test('renders sidebar', () => {
    const devicesCountData = {
      'num_hosts': 3
    };

    const cmmbCapacityData = {
      'total_capacity': 10000
    }

    const cmmbBandwidthData = {
      'max_bandwidth': 32
    }

    const { getByTestId } = render(
      <WebSocketContext.Provider value={{devicesCountData, cmmbCapacityData, cmmbBandwidthData}}>
        <SelectedOptionProvider>
          <App />
        </SelectedOptionProvider>
      </WebSocketContext.Provider>
    );
    expect(getByTestId('sidebar-container')).toBeInTheDocument();
  });
});