import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import '@testing-library/jest-dom';
import App from './App';

// Mock all the page components
jest.mock('./pages/Dashboard', () => {
  return function Dashboard() {
    return <div data-testid="dashboard-page">Dashboard Page</div>;
  };
});

jest.mock('./pages/Configure', () => {
  return function Configure() {
    return <div data-testid="configure-page">Configure Page</div>;
  };
});

jest.mock('./pages/Metrics', () => {
  return function Metrics() {
    return <div data-testid="metrics-page">Metrics Page</div>;
  };
});

jest.mock('./pages/Jobs', () => {
  return function Jobs() {
    return <div data-testid="jobs-page">Jobs Page</div>;
  };
});

jest.mock('./pages/About', () => {
  return function About() {
    return <div data-testid="about-page">About Page</div>;
  };
});

// Mock the components
jest.mock('./components/Header', () => {
  return function Header() {
    return <div data-testid="header">Header Component</div>;
  };
});

jest.mock('./components/SideBar', () => {
  return function SideBar({ children }) {
    return (
      <div data-testid="sidebar">
        <div>SideBar Component</div>
        {children}
      </div>
    );
  };
});

// Mock ProtectedRoute to always render children
jest.mock('./components/ProtectedRoute', () => {
  return function ProtectedRoute({ children, allowedRoles }) {
    return (
      <div data-testid="protected-route" data-allowed-roles={allowedRoles?.join(',') || 'all'}>
        {children}
      </div>
    );
  };
});

// Mock CSS imports
jest.mock('./App.css', () => ({}));
jest.mock('bootstrap/dist/css/bootstrap.min.css', () => ({}));

// Create a test wrapper that doesn't interfere with App's BrowserRouter
const TestWrapper = ({ children, initialEntries = ['/'] }) => {
  return children; // Let App handle its own routing
};

describe('App Component', () => {
  let mockReplaceState;
  let originalLocation;

  beforeEach(() => {
    // Mock window.history.replaceState
    mockReplaceState = jest.fn();
    Object.defineProperty(window, 'history', {
      value: { replaceState: mockReplaceState },
      writable: true,
    });

    // Store original location
    originalLocation = window.location;
  });

  afterEach(() => {
    jest.clearAllMocks();
    // Restore original location
    window.location = originalLocation;
  });

  describe('Basic Rendering', () => {
    it('renders without crashing', () => {
      expect(() => render(<App />)).not.toThrow();
    });

  });

});