import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import '@testing-library/jest-dom';
import App from './App';

// Mock the Home component
jest.mock('./components/Home', () => {
  return function Login() {
    return <div data-testid="login-component"> Home Component</div>;
  };
});

// Mock CSS import
jest.mock('./App.css', () => ({}));

// Test wrapper to provide router context
const TestWrapper = ({ children, initialEntries = ['/'] }) => (
  <MemoryRouter initialEntries={initialEntries}>
    {children}
  </MemoryRouter>
);

describe('App Component', () => {
  it('renders without crashing', () => {
    render(
      <TestWrapper>
        <App />
      </TestWrapper>
    );
  });

  it('renders the main App div with correct className', () => {
    render(
      <TestWrapper>
        <App />
      </TestWrapper>
    );

    const appDiv = document.querySelector('.App');
    expect(appDiv).toBeInTheDocument();
  });

  it('contains Routes component', () => {
    render(
      <TestWrapper>
        <App />
      </TestWrapper>
    );

    // Verify that the Home component renders, which means Routes is working
    expect(screen.getByTestId('login-component')).toBeInTheDocument();
  });

  it('has correct route configuration for root path', () => {
    render(
      <TestWrapper initialEntries={['/']}>
        <App />
      </TestWrapper>
    );

    // When navigating to '/', Home component should render
    expect(screen.getByTestId('login-component')).toBeInTheDocument();
  });

  it('renders App structure correctly', () => {
    const { container } = render(
      <TestWrapper>
        <App />
      </TestWrapper>
    );

    // Check the overall structure
    const appDiv = container.querySelector('.App');
    expect(appDiv).toBeInTheDocument();

    // Home component should be inside the App div
    expect(appDiv).toContainElement(screen.getByTestId('login-component'));
  });

  it('does not render Home component for non-matching routes', () => {
    render(
      <TestWrapper initialEntries={['/non-existent-route']}>
        <App />
      </TestWrapper>
    );

    // Home should not render for unmatched routes
    expect(screen.queryByTestId('login-component')).not.toBeInTheDocument();
  });

  it('maintains App className regardless of route', () => {
    const { rerender } = render(
      <TestWrapper initialEntries={['/']}>
        <App />
      </TestWrapper>
    );

    expect(document.querySelector('.App')).toBeInTheDocument();

    // Re-render with different route
    rerender(
      <TestWrapper initialEntries={['/other']}>
        <App />
      </TestWrapper>
    );

    // App div should still have the className
    expect(document.querySelector('.App')).toBeInTheDocument();
  });

  it('exports App component as default', () => {
    // This test ensures the component is properly exported
    expect(App).toBeDefined();
    expect(typeof App).toBe('function');
  });
});

