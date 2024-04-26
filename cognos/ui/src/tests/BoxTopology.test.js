import React from 'react';
import { render, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import '@testing-library/jest-dom'; 
import BoxTopology from '../components/BoxTopology';

test('renders BoxTopology component', () => {
  render(<BoxTopology />);
});


describe('BoxTopology', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });
  it('fetches hostToDeviceMapping data and renders components correctly', async () => {
    const mockData = [
      { host: 'Host1', devices: ['D1', 'D3', 'D6'] },
      { host: 'Host2', devices: ['D4'] },
      { host: 'Host3', devices: ['D5'] }
    ];

    global.fetch = jest.fn().mockResolvedValueOnce({
      json: () => Promise.resolve(mockData)
    });

    const { getByText } = render(<BoxTopology />);
    await waitFor(() => {
      expect(getByText('H-1')).toBeInTheDocument();
      expect(getByText('H-2')).toBeInTheDocument();
      expect(getByText('H-3')).toBeInTheDocument();
      expect(getByText('D3')).toBeInTheDocument();
      expect(getByText('D4')).toBeInTheDocument();
      expect(getByText('D6')).toBeInTheDocument();
    });
  });

});