/**
 * @jest-environment jsdom
 */

import React from 'react';
import { render, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import { DynamicField } from '../components/forms/dynamicField';

describe('DynamicField component', () => {
  const baseField = {
    field_name: 'username',
    label: 'Username',
    type: 'text',
    required: false,
  };

  test('renders label and input with correct attributes', () => {
    const onChange = jest.fn();
    render(
      <DynamicField
        field={baseField}
        value="john"
        onChange={onChange}
      />
    );

    // Label should be associated with the input via htmlFor/id
    const label = screen.getByLabelText(/Username/i);
    expect(label).toBeInTheDocument();

    // Input should have correct type and placeholder
    expect(label).toHaveAttribute('type', 'text');
    expect(label).toHaveAttribute('placeholder', 'Enter Username');
    expect(label).toHaveValue('john');
  });

  test('shows required indicator when field is required', () => {
    const requiredField = { ...baseField, required: true };
    const onChange = jest.fn();
    render(
      <DynamicField
        field={requiredField}
        value=""
        onChange={onChange}
      />
    );

    // The required asterisk is rendered as a span with class 'required'
    const requiredSpan = screen.getByText((content, element) => {
      return element.tagName.toLowerCase() === 'span' && element.classList.contains('required');
    });
    expect(requiredSpan).toBeInTheDocument();
  });

  test('calls onChange with field name and new value when input changes', () => {
    const onChange = jest.fn();
    render(
      <DynamicField
        field={baseField}
        value=""
        onChange={onChange}
      />
    );

    const input = screen.getByLabelText(/Username/i);
    fireEvent.change(input, { target: { value: 'alice' } });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('username', 'alice');
  });
});