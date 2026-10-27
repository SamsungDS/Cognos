/**
 * @jest-environment jsdom
 */

import React from 'react';
import { render, fireEvent, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Developer from '../pages/Developer';
import { DynamicFormModal } from '../components/forms/dynamicFormModal';

// Mock constants used by the component
jest.mock('../../src/constant', () => ({
  AddIcon: 'add-icon.png',
  CognosMoveAPIArgs: { title: 'move' },
  CognosMoveAllAPIArgs: { title: 'move_all' },
  CognosMoveStatsAPIArgs: { title: 'get_move_stats' },
}));

// Mock the DynamicFormModal to avoid importing the actual implementation
jest.mock('../components/forms/dynamicFormModal', () => ({
    DynamicFormModal: ({ isOpen }) =>
        isOpen
            ? require('react').createElement('div', { 'data-testid': 'dynamic-form-modal' }, 'Mocked Modal')
            : null,
}));

describe('Developer component', () => {
  test('renders main headings', () => {
    render(<Developer />);

    expect(
      screen.getByRole('heading', { name: /Cognos API Sandbox/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /Use this page to test unique features of Cognos./i })
    ).toBeInTheDocument();
  });

  test('renders feature rows in the table', () => {
    render(<Developer />);

    const rows = ['move', 'move_all', 'get_move_stats'];
    rows.forEach((feature) => {
      expect(screen.getByText(feature)).toBeInTheDocument();
    });
  });

  test('opens DynamicFormModal when a feature button is clicked', async () => {
    render(<Developer />);

    // The buttons have no accessible name; locate them by their position
    const buttons = screen.getAllByRole('button');
    // Click the first button (corresponding to "move")
    fireEvent.click(buttons[0]);

    await waitFor(() => {
      expect(screen.getByTestId('dynamic-form-modal')).toBeInTheDocument();
    });
  });

  // test('updates action status after successful form submission', async () => {
  //   // Mock the onSuccess prop inside the component by mocking DynamicFormModal's behavior
  //   const mockOnSuccess = jest.fn((data) => data);
  //   jest.mock('../components/forms/dynamicFormModal', () => ({
  //     DynamicFormModal: ({ isOpen, onSuccess }) => {
  //       if (isOpen) {
  //         // Simulate immediate success callback
  //         onSuccess({ status: 'completed' });
  //       }
  //       return null;
  //     },
  //   }));

  //   render(<Developer />);

  //   // Click the button to open the modal (which will immediately invoke onSuccess)
  //   const buttons = screen.getAllByRole('button');
  //   fireEvent.click(buttons[0]);

  //   await waitFor(() => {
  //     // After success, the status cell for "move" should display "completed"
  //     const statusCell = screen.getByText('completed');
  //     expect(statusCell).toBeInTheDocument();
  //   });
  // });

  // test('closes the modal when onClose is called', async () => {
  //   // Mock DynamicFormModal to expose a close button for testing
  //   // jest.mock('../components/forms/dynamicFormModal', () => ({
  //   //   DynamicFormModal: ({ isOpen, onClose }) =>
  //   //     isOpen ? (
  //   //       <div data-testid="dynamic-form-modal">
  //   //         <button onClick={onClose}>Close Modal</button>
  //   //       </div>
  //   //     ) : null,
  //   // }));

  //   jest.mock('../components/forms/dynamicFormModal', () => ({
  //       DynamicFormModal: ({ isOpen, onClose }) =>
  //           isOpen
  //               ? require('react').createElement(
  //                   'div',
  //                   { 'data-testid': 'dynamic-form-modal' },
  //                   require('react').createElement('button', { onClick: onClose }, 'Close Modal')
  //               )
  //               : null,
  //   }));

  //   render(<Developer />);

  //   const buttons = screen.getAllByRole('button');
  //   fireEvent.click(buttons[0]); // open modal

  //   await waitFor(() => {
  //     expect(screen.getByTestId('dynamic-form-modal')).toBeInTheDocument();
  //   });

  //   fireEvent.click(screen.getByText('Close Modal'));

  //   await waitFor(() => {
  //     expect(screen.queryByTestId('dynamic-form-modal')).not.toBeInTheDocument();
  //   });
  // });
});