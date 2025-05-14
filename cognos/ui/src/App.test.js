import React from 'react';
import { render, screen} from '@testing-library/react';
import App from './App';
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
      <SelectedOptionProvider>
        <App />
      </SelectedOptionProvider>
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
      <SelectedOptionProvider>
        <App />
      </SelectedOptionProvider>
    );
    const headers = screen.queryAllByText(/Cognos Management Console/i);
    expect(headers).toHaveLength(2);
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
      <SelectedOptionProvider>
        <App />
      </SelectedOptionProvider>
    );
    expect(getByTestId('sidebar-container')).toBeInTheDocument();
  });
});