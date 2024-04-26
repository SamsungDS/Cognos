import React from 'react';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Header from '../components/Header';

describe('Header', () => {
  it('renders without crashing', () => {
    render(<Header />);
  });

  it('renders Samsung logo and text', () => {
    const { getByAltText, getByText } = render(<Header />);
    const logo = getByAltText('logo');
    const text = getByText(/Cognos Management Console/i);

    expect(logo).toBeInTheDocument();
    expect(text).toBeInTheDocument();
  });
});