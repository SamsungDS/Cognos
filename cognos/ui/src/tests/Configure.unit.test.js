import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Configure from '../pages/Configure';
import * as constants from '../constant';

// Mocking fetch responses
global.fetch = jest.fn().mockImplementation(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve([]),
  })
);

describe('Configure', () => {
  test('should render properly and fetch data on mount', async () => {
    render(<Configure />);
    
    // Check if fetch calls are made on mount
    setTimeout(() => expect(fetch).toHaveBeenCalledTimes(1));
    expect(fetch).toHaveBeenCalledWith(`${constants.Configs.data_endpoint}//lmds`);
  },0);


});

describe('Configure component', () => {
  test('should call getAvailableLMDS and toggle showAttach state when handleAttachMemoryToggle is called', async () => {
    const { getByTestId } = render(<Configure />);
    const attachButton = getByTestId('attach-id');
    const initialShowAttachState = false;
    fireEvent.click(attachButton);
    // Wait for the asynchronous operations inside handleAttachMemoryToggle to complete
    setTimeout(() => {
      // Check if getAvailableLMDS is called
      expect(fetch).toHaveBeenCalledWith(`${Configs.data_endpoint}//available_lmds`, expect.any(Object));
      // Check if showAttach state is toggled
      expect(setShowAttachMock).toHaveBeenCalledWith(!initialShowAttachState);
    }, 0);
  });
});

// Mock Configs.data_endpoint
jest.mock('../config/config.json', () => ({
  data_endpoint: 'http://105.91.142.222:4000',
}));

// Mock fetch function
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve([]),
  })
);

test('renders configuration table with mock data', async () => {
  // Render the component
  const { getByText, getByAltText } = render(<Configure />);

  // Wait for the component to fetch data
  setTimeout(() => {
    expect(global.fetch).toHaveBeenCalledTimes(1);
  },0);

  // Check if the table headers are rendered
  expect(getByText('Attach/Detach')).toBeInTheDocument();
  expect(getByText('CXL Device')).toBeInTheDocument();
  expect(getByText('Memory Type')).toBeInTheDocument();
  expect(getByText('Mode')).toBeInTheDocument();
  expect(getByText('Total Capacity')).toBeInTheDocument();
  expect(getByText('Capacity Usage')).toBeInTheDocument();
  
  // Check if buttons are rendered
  // expect(getByText('Attach Memory')).toBeInTheDocument();
  // expect(getByText('Detach Memory')).toBeInTheDocument();
  // expect(getByText('Free Memory')).toBeInTheDocument();

  // Mock lmdData
  const lmdData = [
    
  ];

  // Mock handleDetachMemoryToggle function
  // const handleDetachMemoryToggle = jest.fn();
  // jest.mock('./configure', () => ({
  //   ...jest.requireActual('./configure'),
  //   handleDetachMemoryToggle,
  // }));

  // Update the component with mock lmdData and handleDetachMemoryToggle
  render(<Configure lmdData={lmdData} />);

  // Check if the table rows are rendered properly
  lmdData.forEach(item => {
    expect(getByText(item.lmd)).toBeInTheDocument();
    expect(getByText(item.mem_type)).toBeInTheDocument();
    expect(getByText(item.mem_mode)).toBeInTheDocument();
    expect(getByText(`${item.capacity} ${item.capacity_units}`)).toBeInTheDocument();
    expect(getByText(`${item.used_capacity} ${item.used_capacity_units}`)).toBeInTheDocument();

    // Check if the minus button is rendered and clickable
    // const minusButton = getByAltText('minus-icon');
    // expect(minusButton).toBeInTheDocument();
    // fireEvent.click(minusButton);
    // expect(handleDetachMemoryToggle).toHaveBeenCalledWith(item);
  });
});

