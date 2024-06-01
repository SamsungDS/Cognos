import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import AttachMemory from '../components/popups/AttachMemory';

describe('AttachMemory', () => {
  test('should render properly and call onSave with correct data', () => {
    const onSave = jest.fn();
    const onCancel = jest.fn();
    const availableLMDs = ['D-1', 'D-2'];

    const { getByLabelText, getByText, } = render(
      <AttachMemory show={true} onSave={onSave} onCancel={onCancel} availableLMDs={availableLMDs} />
    );

    const selectCxlDevice = getByLabelText('Select CXL Device');
    const memoryMode = getByLabelText('Memory Mode');
    const attachButton = getByText('Attach');

    fireEvent.change(selectCxlDevice, { target: { value: 'D-1' } });
    fireEvent.change(memoryMode, { target: { value: 'direct' } });
    fireEvent.click(attachButton);

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith({
      dev_name: 'D-1'
    });
  });

  test('should call onCancel when Cancel button is clicked', () => {
    const onSave = jest.fn();
    const onCancel = jest.fn();
    const availableLMDs = ['D-1', 'D-2'];

    const { getByText, getByTestId, getByLabelText } = render(
      <AttachMemory show={true} onSave={onSave} onCancel={onCancel} availableLMDs={availableLMDs} />
    );

    // Find the button to toggle advanced memory settings
    const toggleButton = getByTestId('Advanced Memory Settings');

    // Ensure the button is found
    expect(toggleButton).toBeInTheDocument();

    // Click the button to toggle advanced memory settings
    fireEvent.click(toggleButton);

    // After clicking the button, host memory address input should be rendered
    expect(getByLabelText('start offset')).toBeInTheDocument();

    const cancelButton = getByText('Cancel');

    fireEvent.click(cancelButton);

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
