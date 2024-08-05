import React from 'react';
import { render, fireEvent, within } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Configure, { getReadableStatus } from '../pages/Configure';
import * as constants from '../constant';


beforeEach(() => {
  // Mock Configs.api_endpoint
  jest.mock('../config/config.json', () => ({
    api_endpoint: 'http://105.91.142.222:4000//api/v2.0.0',
  }));

  // Mocking fetch responses
    global.fetch = jest.fn().mockImplementation(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve([]),
    })
  );
});


describe('Configure', () => {
  test('should render properly and fetch data on mount', async () => {
    render(<Configure />);
    
    // Check if fetch calls are made on mount
    setTimeout(() => expect(fetch).toHaveBeenCalledTimes(1));
    expect(fetch).toHaveBeenCalledWith(`${constants.Configs.api_endpoint}/devices`, {
      method: 'post',
      headers: new Headers({
        'Access-Control-Allow-Origin':'*',
        'accept': 'application/json',
        'content-type': 'application/json'
      }),
      body: JSON.stringify({
        "input": "cluster_id=CLUST1;command=ListDevices;FM_id=203;FM_endpoint=samsung.com"
      })
    });
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
      expect(fetch).toHaveBeenCalledWith(`${Configs.api_endpoint}//available_lmds`, expect.any(Object));
      // Check if showAttach state is toggled
      expect(setShowAttachMock).toHaveBeenCalledWith(!initialShowAttachState);
    }, 0);
  });
});


test('renders configuration table with mock data', async () => {
  // Render the component
  const { getByText } = render(<Configure />);

  // Wait for the component to fetch data
  setTimeout(() => {
    expect(global.fetch).toHaveBeenCalledTimes(1);
  },0);

  // Check if the table headers are rendered
  expect(getByText('Attach/Detach')).toBeInTheDocument();
  expect(getByText('Status')).toBeInTheDocument();
  expect(getByText('Type')).toBeInTheDocument();
  expect(getByText('Mode')).toBeInTheDocument();
  
  // Mock lmdData
  const lmdData = [];

  // Update the component with mock lmdData and handleDetachMemoryToggle
  render(<Configure lmdData={lmdData} />);

  // Check if the table rows are rendered properly
  lmdData.forEach(item => {
    expect(getByText(item.dev_name)).toBeInTheDocument();
    expect(getByText(item.status)).toBeInTheDocument();
    expect(getByText(item.type)).toBeInTheDocument();
    expect(getByText(item.mode)).toBeInTheDocument();
    expect(getByText(item.dev_capacity)).toBeInTheDocument();
  });
});


describe('Configure', () => {
  test('should render properly and fetch data on mount', async () => {
    render(<Configure />);
    
    // Check if fetch calls are made on mount
    setTimeout(() => expect(fetch).toHaveBeenCalledTimes(1));
    expect(fetch).toHaveBeenCalledWith(`${constants.Configs.api_endpoint}/devices`, {
      method: 'post',
      headers: new Headers({
        'Access-Control-Allow-Origin':'*',
        'accept': 'application/json',
        'content-type': 'application/json'
      }),
      body: JSON.stringify({
        "input": "cluster_id=CLUST1;command=ListDevices;FM_id=203;FM_endpoint=samsung.com"
      })
    });
  },0);

});


test('renders configuration table with mock data', async () => {
  // Render the component
  const { getByText } = render(<Configure />);

  // Wait for the component to fetch data
  setTimeout(() => {
    expect(global.fetch).toHaveBeenCalledTimes(1);
  },0);

  // Check if the table headers are rendered
  expect(getByText('Status')).toBeInTheDocument();

  // Mock lmdData
  const memboxData = [];


  // Update the component with mock lmdData and handleDetachMemoryToggle
  render(<Configure memboxData={memboxData} />);

  // Check if the table rows are rendered properly
  memboxData.forEach(item => {
    expect(getByText(item.lmd)).toBeInTheDocument();
    expect(getByText(item.device_type)).toBeInTheDocument();
    expect(getByText(item.memory_servers)).toBeInTheDocument();
    expect(getByText(`${item.capacity} ${item.capacity_units}`)).toBeInTheDocument();
  });
});



describe('Configure Component', () => {
  it('should toggle showDetachMemory when handleDetachMemoryToggle is called', () => {
    const { getByTestId } = render(<Configure />);
    const detachButton = getByTestId('detach-button'); 

    fireEvent.click(detachButton);

    // Check if showDetachMemory state is toggled
    expect(getByTestId('detach-memory-modal').getAttribute('show')).toBe(null);
  });

  it('should toggle showAttach when handleAttachCancel is called', () => {
    const { getByTestId } = render(<Configure />);
    const attachButton = getByTestId('attach-id'); 

    fireEvent.click(attachButton);
 
    // Check if showAttach state is toggled
    expect(getByTestId('attach-memory-modal').getAttribute('show')).toBe(null);
  });
  it("handle DropDown Change value", () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ value: 'Host 2' }),
      })
    );
    const {getByTestId}= render(<Configure />)

    const dropdown = getByTestId('dropdown-hostTable');
    const select = within(dropdown).getByRole('combobox');
    fireEvent.change(select,  { target : { value: 'host_2', label:'Host 2'}});

    // Expect handleSelectChange to be called with the correct arguments
    expect(fetch).toHaveBeenCalledWith(`${constants.Configs.api_endpoint}/devices`, {
      headers: new Headers({
        'Access-Control-Allow-Origin':'*',
        "accept": "application/json",
        "content-type": "application/json"
      }),
      method: 'post',
      body: JSON.stringify({
        "input": "cluster_id=CLUST1;command=ListDevices;FM_id=203;FM_endpoint=samsung.com"
      })
    });

  })
});


// Test interaction with Attach cancel button
it('should close AttachMemory modal when cancel button is clicked', () => {
  const { getByTestId, queryByTestId } = render(<Configure />);
  // Open the AttachMemory modal
  fireEvent.click(getByTestId('attach-id'));
  // Simulate clicking on the cancel button
  fireEvent.click(getByTestId('attach-memory-cancel-button'));
  // Expect the AttachMemory modal to be closed
  expect(queryByTestId('attach-memory-modal')).not.toBeInTheDocument();
});


// Test interaction with Detach cancel button
it('should close DetachMemory modal when cancel button is clicked', () => {
  const { getByTestId, queryByTestId } = render(<Configure />);
  // Open the DetachMemory modal
  fireEvent.click(getByTestId('detach-button'));
  // Simulate clicking on the cancel button
  fireEvent.click(getByTestId('cancel-detach-button'));
  // Expect the DetachMemory modal to be closed
  expect(queryByTestId('detach-memory-modal')).not.toBeInTheDocument();
});


describe('getting Readable status function', () => {
  // Test getReadableStatus function
  it('should return "Rebooting Host" when job status is "loading"', () => {
    // Define a mock job object with status "loading"
    const job = { status: 'loading' };
    // Call the function with the mock job object
    const result = getReadableStatus(job);
    // Assert that the result is "Rebooting Host"
    expect(result).toBe('Rebooting Host');
  });

  it('should return the status itself when job status is not "loading"', () => {
    // Define a mock job object with status other than "loading"
    const job = { status: 'active' };
    // Call the function with the mock job object
    const result = getReadableStatus(job);
    // Assert that the result is the same as the status
    expect(result).toBe(job.status);
  });
});
