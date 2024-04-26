import React from 'react';
import '@testing-library/jest-dom/extend-expect';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SideBar from '../components/SideBar';

describe('SideBar', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <SideBar />
      </MemoryRouter>
    );
  });

  it('renders menu items with icons and links', async () => {
    const { getByTestId } = render(
      <MemoryRouter>
        <SideBar />
      </MemoryRouter>
    );

    await waitFor(() => {
      // Check for the presence of the icons
      expect(getByTestId('menu-item-0')).toBeInTheDocument();
      expect(getByTestId('menu-item-1')).toBeInTheDocument();
      expect(getByTestId('menu-item-2')).toBeInTheDocument();
      expect(getByTestId('menu-item-3')).toBeInTheDocument();

    });
  });
});