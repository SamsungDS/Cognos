import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import DetachMemory from '../components/popups/DetachMemory';

describe('DetachMemory component', () => {
  test('renders with correct content', () => {
    const { getByText } = render(
      <DetachMemory
        show={true}
        rowData={{ lmd: 'memoryDeviceId' }}
        onCancel={() => {}}
        onDelete={() => {}}
      />
    );

    expect(getByText('Detach Memory')).toBeInTheDocument();
    expect(
      getByText('Are you sure you want to detach logical Memory Device from Host ?')
    ).toBeInTheDocument();
    expect(getByText('Cancel')).toBeInTheDocument();
    expect(getByText('Detach')).toBeInTheDocument();
  });

  test('calls onCancel when cancel button is clicked', () => {
    const onCancelMock = jest.fn();
    const { getByText } = render(
      <DetachMemory
        show={true}
        rowData={{ lmd: 'D-1' }}
        onCancel={onCancelMock}
        onDelete={() => {}}
      />
    );

    fireEvent.click(getByText('Cancel'));
    expect(onCancelMock).toHaveBeenCalled();
  });

  test('calls onDelete with correct parameter when detach button is clicked', () => {
    const onDeleteMock = jest.fn();
    const { getByText } = render(
      <DetachMemory
        show={true}
        rowData={{ dev_name: 'D-1' }}
        onCancel={() => {}}
        onDelete={onDeleteMock}
      />
    );

    fireEvent.click(getByText('Detach'));
    expect(onDeleteMock).toHaveBeenCalledWith('D-1');
  });

  test('does not render when show prop is false', () => {
    const { queryByText } = render(
      <DetachMemory
        show={false}
        rowData={{ lmd: 'D-1' }}
        onCancel={() => {}}
        onDelete={() => {}}
      />
    );

    expect(queryByText('Detach Memory')).not.toBeInTheDocument();
  });
});