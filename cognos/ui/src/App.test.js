import React from 'react';
import { render} from '@testing-library/react';
import App from './App';
import WebSocketContext from './contexts/WebSocketContext';

describe('App', () => {
  it('renders without crashing', () => {
    // const [devicesCountData, setDevicesCountData] = useState([]);
    // const setDevicesCountData = jest.fn();
    // const useStateSpy = jest.spyOn(React, 'useState');
    // useStateSpy.mockImplementation((devicesCountData) => [devicesCountData, setDevicesCountData]);    
    // setDevicesCountData({
    //   "num_hosts": 1
    // })

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
        <App />
      </WebSocketContext.Provider>
    );
  });

  it('renders header', () => {

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
        <App />
      </WebSocketContext.Provider>
    );
    expect(getByText(/Cognos Management Console/i)).toBeInTheDocument();
  });

  it('renders sidebar', () => {
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
        <App />
      </WebSocketContext.Provider>
    );
    expect(getByTestId('sidebar-container')).toBeInTheDocument();
  });
});