/**
 * @jest-environment jsdom
 */

import React from 'react';
import { render, fireEvent, waitFor, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import { DynamicFormModal } from '../components/forms/dynamicFormModal';

// Mock the fetch API used inside the component
global.fetch = jest.fn();

const mockConfig = {
  title: 'Test Job',
  endpoint: '/api/launch',
  fields: [
    { field_name: 'name', label: 'Name', type: 'text' },
    { field_name: 'count', label: 'Count', type: 'number' },
  ],
};

describe('DynamicFormModal', () => {
  const onClose = jest.fn();
  const onSuccess = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    onClose.mockClear();
    onSuccess.mockClear();
  });

  test('renders modal with title and fields', () => {
    render(
      <DynamicFormModal
        config={mockConfig}
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    // Title should be visible
    expect(screen.getByText(/Configure Job: Test Job/i)).toBeInTheDocument();

    // Fields from config should be rendered
    mockConfig.fields.forEach((field) => {
      expect(screen.getByLabelText(field.label)).toBeInTheDocument();
    });
  });

  test('updates form data when inputs change', () => {
    render(
      <DynamicFormModal
        config={mockConfig}
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    const nameInput = screen.getByLabelText('Name');
    const countInput = screen.getByLabelText('Count');

    fireEvent.change(nameInput, { target: { value: 'Sample' } });
    fireEvent.change(countInput, { target: { value: '42' } });

    expect(nameInput).toHaveValue('Sample');
    expect(countInput).toHaveValue(42);
  });

  test('calls API and handles success response', async () => {
    const mockResponse = { status: 'ok', data: {} };
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    });

    render(
      <DynamicFormModal
        config={mockConfig}
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    // Fill in form fields
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'JobName' },
    });
    fireEvent.change(screen.getByLabelText('Count'), {
      target: { value: '5' },
    });

    // Submit the form
    fireEvent.click(screen.getByText('Launch Job'));

    // Loading spinner should appear
    expect(screen.getByText('Launching...')).toBeInTheDocument();

    // Await the async submit handling
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining(mockConfig.endpoint),
        expect.objectContaining({
          method: 'POST',
          headers: expect.any(Headers),
          body: JSON.stringify({
            name: 'JobName',
            count: '5',
          }),
        })
      );
    });

    // onSuccess and onClose callbacks should be called
    expect(onSuccess).toHaveBeenCalledWith(mockResponse);
    expect(onClose).toHaveBeenCalled();
  });

  test('displays error message on API failure', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    render(
      <DynamicFormModal
        config={mockConfig}
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    fireEvent.click(screen.getByText('Launch Job'));

    await waitFor(() => {
      // The component should show an alert with the error message
      expect(screen.getByRole('alert')).toHaveTextContent('HTTP 500');
    });

    // Ensure callbacks are not called on failure
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  test('closes modal when Cancel button is clicked', () => {
    render(
      <DynamicFormModal
        config={mockConfig}
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    fireEvent.click(screen.getByText('Cancel'));

    expect(onClose).toHaveBeenCalled();
  });
});