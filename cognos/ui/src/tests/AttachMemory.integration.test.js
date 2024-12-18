import React, {useState} from 'react';
import { render, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import AttachMemory from '../components/popups/AttachMemory';
import * as constant from '../constant';

describe('AttachMemory', () => {
  test('should render properly and call onSave with correct data', () => {
    const onSave = jest.fn();
    const onCancel = jest.fn();
    const availableLMDs = ['DEVX', 'D-2'];
    const selectedValue = 'host1';
    const logicalMemoryDevice = 'DEVX';
    const setLogicalMemoryDevice = jest.fn();

    const { getByLabelText, getByText, } = render(
      <AttachMemory 
        show={true} onSave={onSave} onCancel={onCancel} availableLMDs={availableLMDs}
        selectedValue={selectedValue} logicalMemoryDevice={logicalMemoryDevice}
        setLogicalMemoryDevice={setLogicalMemoryDevice}
      />
    );

    const selectCxlDevice = screen.getByLabelText('Select CXL Device');
    const memoryMode = screen.getByLabelText('Memory Mode');
    const applicationServer = screen.getByLabelText('Application Server');
    expect(applicationServer).toBeInTheDocument();
    const attachButton = screen.getByText('Attach');

    fireEvent.change(selectCxlDevice, { target: { value: constant.deviceName } });
    fireEvent.change(memoryMode, { target: { value: constant.deviceMode } });
    fireEvent.click(attachButton);

    
    // Find the button to toggle advanced memory settings
    const toggleButton = screen.getByTestId('Advanced Memory Settings');

    // Ensure the button is found
    expect(toggleButton).toBeInTheDocument();

    // Click the button to toggle advanced memory settings
    fireEvent.click(toggleButton);

    const inputElement = screen.getByLabelText('start offset');
    // Check initial value
    expect(inputElement.value).toBe('');
    // Simulate user typing in the input
    fireEvent.change(inputElement, { target: { value: '0x1234' } });

    // Check if the value is updated
    expect(inputElement.value).toBe('0x1234');

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith({
      dev_name: 'DEVX'
    });
  });

  test('should call onCancel when Cancel button is clicked', () => {
    const onSave = jest.fn();
    const onCancel = jest.fn();
    const availableLMDs = ['DEVX', 'D-2'];
    const selectedValue = 'host1';
    const logicalMemoryDevice = 'DEVX';
    const setLogicalMemoryDevice = jest.fn();

    const { getByText, getByTestId, getByLabelText } = render(
      <AttachMemory 
        show={true} onSave={onSave} onCancel={onCancel} availableLMDs={availableLMDs}
        selectedValue={selectedValue} logicalMemoryDevice={logicalMemoryDevice}
        setLogicalMemoryDevice={setLogicalMemoryDevice}
      />
    );

    // Find the button to toggle advanced memory settings
    const toggleButton = screen.getByTestId('Advanced Memory Settings');

    // Ensure the button is found
    expect(toggleButton).toBeInTheDocument();

    // Click the button to toggle advanced memory settings
    fireEvent.click(toggleButton);

    // After clicking the button, host memory address input should be rendered
    expect(screen.getByLabelText('start offset')).toBeInTheDocument();

    const cancelButton = screen.getByText('Cancel');

    fireEvent.click(cancelButton);

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
