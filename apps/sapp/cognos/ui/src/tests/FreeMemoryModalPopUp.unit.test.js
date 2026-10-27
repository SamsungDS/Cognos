import React from 'react';
import { render, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import FreeMemoryModalPopup from '../components/popups/FreeMemoryModalPopUp';

describe('FreeMemoryModalPopup', () => {
  const onCancel = jest.fn();
  const onUpdate = jest.fn();
  const onDelete = jest.fn();
  const rowData = {
    lmd: 'D-1',
    mem_type: 'CMMD',
    mem_mode: 'Direct'
  };
  
  it('renders with correct initial values', () => {
    const { getByLabelText } = render(
      <FreeMemoryModalPopup
        show={true}
        rowData={rowData}
        onCancel={onCancel}
        onUpdate={onUpdate}
        onDelete={onDelete}
      />
    );

    expect(getByLabelText('Logical Memory Device')).toHaveValue('D-1');
    expect(getByLabelText('Memory Type')).toHaveValue('CMMD');
    expect(getByLabelText('Memory Mode')).toHaveValue('Direct');
  });

  it('calls onCancel when Cancel button is clicked', () => {
    const { getByText } = render(
      <FreeMemoryModalPopup
        show={true}
        rowData={rowData}
        onCancel={onCancel}
        onUpdate={onUpdate}
        onDelete={onDelete}
      />
    );

    fireEvent.click(getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onDelete with correct arguments when Free Memory button is clicked', () => {
    const { getByTestId } = render(
      <FreeMemoryModalPopup
        show={true}
        rowData={rowData}
        onCancel={onCancel}
        onUpdate={onUpdate}
        onDelete={onDelete}
      />
    );

    fireEvent.click(getByTestId('free-memory-button'));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledWith('D-1');
  });
});

describe('FreeMemoryModalPopup', () => {
  it('should handle logical memory device change', () => {
    const setLogicalMemoryDeviceMock = jest.fn();
    const onCancel = jest.fn();
    const onDelete = jest.fn();
    const rowData = { lmd: 'D-1' };

    const { getByLabelText } = render(
      <FreeMemoryModalPopup
        show={true}
        rowData={rowData}
        onCancel={onCancel}
        onUpdate={() => {}}
        onDelete={onDelete}
        setLogicalMemoryDevice = {setLogicalMemoryDeviceMock}
      />
    );

    const inputElement = screen.getByPlaceholderText('Logical Memory Device');

    fireEvent.change(inputElement, { target: { value: 'New Value' } });

    expect(inputElement.value).toBe('New Value');

    const selectElement = screen.getByLabelText('Memory Mode');

    fireEvent.change(selectElement, { target: { value: 'Shared' } });

    expect(selectElement.value).toBe('Shared');
  });
});