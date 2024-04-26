import React from 'react';
import { render} from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renders without crashing', () => {
    render(
        <App />
    );
  });

  it('renders header', () => {
    const { getByText } = render(<App />);
    expect(getByText(/Cognos Management Console/i)).toBeInTheDocument();
  });

  it('renders sidebar', () => {
    const { getByTestId } = render(<App />);
    expect(getByTestId('sidebar-container')).toBeInTheDocument();
  });
});