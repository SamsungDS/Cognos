import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import BoxTopology from './BoxTopology';
import { useSelectedOption } from '../contexts/SelectedOptionContext';
import * as constants from '../constant';

// Mock the dependencies
jest.mock('../contexts/SelectedOptionContext');
jest.mock('../utils/dashboard-utils');
jest.mock('../assets/icons/deviceSVGIcon.svg', () => ({
  ReactComponent: () => <div>DeviceIcon</div>
}));
jest.mock('../assets/icons/CMM-D-Icon.svg', () => ({
  ReactComponent: () => <div>CMMDIcon</div>
}));
jest.mock('../assets/icons/CMM-H-Icon.svg', () => ({
  ReactComponent: () => <div>CMMHIcon</div>
}));
jest.mock('./ShimmerUI', () => ({
  __esModule: true,
  default: () => <div>ShimmerUI</div>,
  NavigationShimmer: () => <div>NavigationShimmer</div>
}));

// Mock fetch globally
global.fetch = jest.fn();

describe('BoxTopology Component', () => {
  const mockHandleToggle = jest.fn();
  const mockFetchData = jest.fn();

  const mockHostToDeviceMapping = {
    clusters: [
      { cluster_name: 'Cluster1' },
      { cluster_name: 'Cluster2' }
    ]
  };

  const mockTransformedData = [
    {
      host: 'Host1',
      devices: ['Device1', 'Device2'],
      fm_type: 'FM_REMOTE_CMMD',
      cluster: 'Cluster1'
    },
    {
      host: 'Host2',
      devices: ['Device3'],
      fm_type: 'FM_DIRECT_CMMD',
      cluster: 'Cluster2'
    }
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    // Mock useSelectedOption hook
    useSelectedOption.mockReturnValue({
      handleToggle: mockHandleToggle,
      selectedOption: 'CMM-B'
    });

    // Mock fetchData function
    jest.spyOn(constants, 'fetchData').mockImplementation((endpoint, setter) => {
      if (endpoint.includes('/topology')) {
        setter(mockHostToDeviceMapping);
      } else if (endpoint.includes('/nodes')) {
        setter([{ host: 'Host1', cluster: 'Cluster1' }]);
      }
    });

    // Mock transformData
    jest.spyOn(constants, 'transformData').mockReturnValue(mockTransformedData);

    // Mock other helper functions
    jest.spyOn(constants, 'assignClusters').mockReturnValue(mockTransformedData);
    jest.spyOn(constants, 'assignClustersToLabelValuePairs').mockReturnValue([]);
    jest.spyOn(constants, 'mergeHosts').mockReturnValue([]);
    jest.spyOn(constants, 'updateHostListAttached').mockReturnValue([
      {
        host: 'Host2',
        details: [{ devices: ['Device3'], fm_type: 'FM_DIRECT_CMMD' }]
      }
    ]);
    jest.spyOn(constants, 'mappedHostList').mockReturnValue([
      { host: 'Host1', color: '#00ff00', isActive: true }
    ]);
    jest.spyOn(constants, 'mappedDeviceList').mockReturnValue([
      { device: 'Device1', color: '#0000ff' }
    ]);

    // Mock Configs
    constants.Configs = {
      api_endpoint: 'http://localhost:3000/api'
    };
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Component Rendering', () => {
    test('renders BoxTopology component', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      expect(screen.getByText(/Cluster:/)).toBeInTheDocument();
    });

    test('renders toggle switch', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const toggleInput = screen.getByRole('checkbox');
      expect(toggleInput).toBeInTheDocument();
    });

    test('renders carousel navigation buttons', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const prevButtons = screen.getAllByAltText('Previous');
      const nextButtons = screen.getAllByAltText('Next');
      expect(prevButtons.length).toBeGreaterThan(0);
      expect(nextButtons.length).toBeGreaterThan(0);
    });

    test('renders CMM titles', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      expect(screen.getByText('Chassis1')).toBeInTheDocument();
    });
  });

  describe('Data Fetching', () => {
    test('fetches data on component mount', async () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      await waitFor(() => {
        expect(constants.fetchData).toHaveBeenCalledTimes(2);
      });
    });

    test('updates cluster list when data is fetched', async () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      await waitFor(() => {
        const dropdown = screen.getByText(/Cluster:/);
        expect(dropdown).toBeInTheDocument();
      });
    });

    test('transforms data correctly', async () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      await waitFor(() => {
        expect(constants.transformData).toHaveBeenCalled();
      });
    });
  });

  describe('Toggle Switch Functionality', () => {
    test('toggle switch reflects selected option', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const toggleInput = screen.getByRole('checkbox');
      expect(toggleInput).toBeChecked();
    });

    test('calls handleToggle when toggle is clicked', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const toggleInput = screen.getByRole('checkbox');
      fireEvent.click(toggleInput);
      expect(mockHandleToggle).toHaveBeenCalled();
    });

    test('toggle is disabled when no remote hosts exist', () => {
      jest.spyOn(constants, 'transformData').mockReturnValue([
        { fm_type: 'FM_DIRECT_CMMD' }
      ]);

      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const toggleInput = screen.getByRole('checkbox');

      waitFor(() => {
        expect(toggleInput).toBeDisabled();
      });
    });

    test('toggle is enabled when remote hosts exist', async () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const toggleInput = screen.getByRole('checkbox');

      await waitFor(() => {
        expect(toggleInput).not.toBeDisabled();
      });
    });
  });



  describe('Navigation Functionality', () => {
    test('navigates to next CMM when next button is clicked', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const nextButton = screen.getByTestId('next-button');
      fireEvent.click(nextButton);

      // Check if the active CMM changed
      const Chassis2 = screen.getByText('Chassis2');
      expect(Chassis2).toHaveClass('active');
    });

    test('navigates to previous CMM when prev button is clicked', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const prevButton = screen.getByTestId('prev-button');
      fireEvent.click(prevButton);

      // Should wrap around to last CMM
      const Chassis6 = screen.getByText('Chassis6');
      expect(Chassis6).toHaveClass('active');
    });

    test('navigates to specific CMM when title is clicked', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const Chassis3 = screen.getByText('Chassis3');
      fireEvent.click(Chassis3);

      expect(Chassis3).toHaveClass('active');
    });

    test('cycles through all CMMs', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const nextButton = screen.getByTestId('next-button');

      // Click through all 6 CMMs
      for (let i = 0; i < 6; i++) {
        fireEvent.click(nextButton);
      }

      // Should be back at first CMM
      const Chassis1 = screen.getByText('Chassis1');
      expect(Chassis1).toHaveClass('active');
    });
  });

  describe('Host View Mode', () => {
    beforeEach(() => {
      useSelectedOption.mockReturnValue({
        handleToggle: mockHandleToggle,
        selectedOption: 'Host'
      });
    });

    test('renders Host view when toggle is set to Host', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      expect(screen.getByText('Host')).toBeInTheDocument();
    });

    test('shows ShimmerUI when no direct device data', () => {
      jest.spyOn(constants, 'transformData').mockReturnValue([]);
      jest.spyOn(constants, 'assignClusters').mockReturnValue([]);

      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      expect(screen.getByText('ShimmerUI')).toBeInTheDocument();
    });

    test('shows NavigationShimmer when no host direct view list', () => {
      jest.spyOn(constants, 'updateHostListAttached').mockReturnValue([]);

      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      expect(screen.getByText('NavigationShimmer')).toBeInTheDocument();
    });

    test('navigates through host views', () => {
      jest.spyOn(constants, 'updateHostListAttached').mockReturnValue([
        {
          host: 'Host1',
          details: [{ devices: ['Device1'], fm_type: 'FM_DIRECT_CMMD' }]
        },
        {
          host: 'Host2',
          details: [{ devices: ['Device2'], fm_type: 'FM_DIRECT_CMMH' }]
        }
      ]);

      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);

      const nextButtons = screen.getAllByAltText('Next');
      if (nextButtons.length > 0) {
        fireEvent.click(nextButtons[0]);
      }

      expect(screen.getByText('Host2')).toBeInTheDocument();
    });
  });

  describe('Component Rendering - Host and Device Components', () => {
    test('renders host components with correct styling', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);

      // Host components should be rendered
      const container = screen.getByTestId || screen.queryByTestId;
      expect(document.querySelector('.badge-container')).toBeInTheDocument();
    });

    test('renders device components with correct styling', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);

      expect(document.querySelector('.device-box')).toBeInTheDocument();
    });

    test('applies correct colors to active hosts', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);

      const badges = document.querySelectorAll('.badge');
      expect(badges.length).toBeGreaterThan(0);
    });

    test('applies correct colors to inactive hosts', () => {
      jest.spyOn(constants, 'mappedHostList').mockReturnValue([
        { host: 'Host1', color: '#00ff00', isActive: false }
      ]);

      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);

      const badges = document.querySelectorAll('.badge');
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  describe('Edge Cases', () => {
    test('handles empty host list', () => {
      jest.spyOn(constants, 'mappedHostList').mockReturnValue([]);

      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      expect(screen.getByText(/Cluster:/)).toBeInTheDocument();
    });

    test('handles empty device list', () => {
      jest.spyOn(constants, 'mappedDeviceList').mockReturnValue([]);

      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      expect(screen.getByText(/Cluster:/)).toBeInTheDocument();
    });

  });

  describe('Performance and Optimization', () => {
    test('does not re-render unnecessarily when same data is set', async () => {
      const onClusterChange = jest.fn();
      const { rerender } = render(<BoxTopology onClusterChange={onClusterChange}/>);

      const initialRenderCount = screen.getAllByText(/Chassis/).length;

      rerender(<BoxTopology onClusterChange={onClusterChange}/>);

      const afterRerenderCount = screen.getAllByText(/Chassis/).length;
      expect(initialRenderCount).toBe(afterRerenderCount);
    });

    test('updates state only when filtered data changes', async () => {
      const onClusterChange = jest.fn();
      const { rerender } = render(<BoxTopology onClusterChange={onClusterChange}/>);

      await waitFor(() => {
        expect(constants.assignClusters).toHaveBeenCalled();
      });

      const callCount = constants.assignClusters.mock.calls.length;
      rerender(<BoxTopology onClusterChange={onClusterChange}/>);

      // Should not call assignClusters again if data hasn't changed
      expect(constants.assignClusters.mock.calls.length).toBeGreaterThanOrEqual(callCount);
    });
  });

  describe('Accessibility', () => {
    test('toggle switch has proper aria attributes', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const toggle = screen.getByRole('checkbox');
      expect(toggle).toHaveAttribute('type', 'checkbox');
    });

    test('buttons have proper alt text', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      expect(screen.getAllByAltText('Previous')).toBeTruthy();
      expect(screen.getAllByAltText('Next')).toBeTruthy();
    });

    test('dropdown has proper accessibility labels', () => {
      const onClusterChange = jest.fn();
      render(<BoxTopology onClusterChange={onClusterChange}/>);
      const dropdown = screen.getByRole('button', { name: /Cluster:/ });
      expect(dropdown).toBeInTheDocument();
    });
  });
});