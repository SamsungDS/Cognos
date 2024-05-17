import React from 'react';
import { render, fireEvent, screen } from '@testing-library/react';
import CreateMemory from '../components/popups/CreateMemory';

describe('CreateMemory component', () => {
  it('renders correctly', () => {
    const onCancel = jest.fn();
    const onSave = jest.fn();
    const show = true;

    const { getByText, getByLabelText } = render(
      <CreateMemory onCancel={onCancel} onSave={onSave} show={show} />
    );

    expect(getByText('Create Logical Memory Device')).toBeInTheDocument();
    expect(getByLabelText('Logical Memory Device')).toBeInTheDocument();
    expect(getByLabelText('Memory Type')).toBeInTheDocument();
    expect(getByLabelText('isPool')).toBeInTheDocument();
    expect(getByLabelText('Pool')).toBeInTheDocument();
    expect(getByText('Memory Allocation 0 GB')).toBeInTheDocument();
    expect(getByText('Create')).toBeInTheDocument();
    expect(getByText('Cancel')).toBeInTheDocument();
  });

  it('calls onSave with form data on save click', () => {
    const onCancel = jest.fn();
    const onSave = jest.fn();
    const show = true;

    const { getByText, getByLabelText } = render(
      <CreateMemory onCancel={onCancel} onSave={onSave} show={show} />
    );

    fireEvent.change(getByLabelText('Logical Memory Device'), {
      target: { value: 'D-1' }
    });
    fireEvent.change(getByLabelText('Pool'), {
      target: { value:  'Pool 1' }
    });

    fireEvent.click(getByText('Create'));

    expect(onSave).toHaveBeenCalledWith({
      logicalMemoryDevice: 'D-1',
      hostMemoryAddress: '',
      memoryType: 'CMMD',
      memoryMode: 'Direct',
      pool: 'Default Pool',
      memoryAllocation: 0,
      isPoolFlag: false
    });

    const selectElement = screen.getByLabelText('Memory Type');

    fireEvent.change(selectElement, { target: { value: 'CMMD' } });

    expect(selectElement.value).toBe('CMMD');
  });

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = jest.fn();
    const onSave = jest.fn();
    const show = true;

    const { getByText } = render(
      <CreateMemory onCancel={onCancel} onSave={onSave} show={show} />
    );

    fireEvent.click(getByText('Cancel'));

    expect(onCancel).toHaveBeenCalled();
  });
});