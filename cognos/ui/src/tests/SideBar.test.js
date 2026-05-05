import React from 'react';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import '@testing-library/jest-dom';
import SideBar from '../components/SideBar.js';
import { AuthContext } from '../components/ProtectedRoute.js';

jest.mock('../constant', () => ({
  Configs: {
    rbac_enabled: true,  // Force RBAC on during tests
  },
}));
// Mock the SVG components

jest.mock('../assets/icons/DashboardIcon.svg', () => ({
  ReactComponent: () => <div data-testid="dashboard-icon">Dashboard Icon</div>
}));

jest.mock('../assets/icons/ChartIcon.svg', () => ({
  ReactComponent: () => <div data-testid="metrics-icon">Metrics Icon</div>
}));

jest.mock('../assets/icons/AboutIcon.svg', () => ({
  ReactComponent: () => <div data-testid="about-icon">About Icon</div>
}));

jest.mock('../assets/icons/AutoTierIcon.svg', () => ({
  ReactComponent: () => <div data-testid="autotier-icon">AutoTier Icon</div>
}));

// Test wrapper component to provide AuthContext and Router
const TestWrapper = ({ userRole, children }) => (
  <BrowserRouter>
    <AuthContext.Provider value={{ userRole }}>
      {children}
    </AuthContext.Provider>
  </BrowserRouter>
);

describe('SideBar Component', () => {
  it('renders sidebar container with correct structure', () => {
    render(
      <TestWrapper userRole="admin">
        <SideBar />
      </TestWrapper>
    );

    const sidebarContainer = screen.getByTestId('sidebar-container');
    expect(sidebarContainer).toBeInTheDocument();
    expect(sidebarContainer).toHaveAttribute('id', 'side-bar-id');
    expect(sidebarContainer).toHaveStyle('width: 50px');
  });

  it('renders all menu items for admin user', () => {
    render(
      <TestWrapper userRole="admin">
        <SideBar />
      </TestWrapper>
    );

    // All menu items should be visible for admin
    expect(screen.getByTestId('menu-item-0')).toBeInTheDocument(); // Dashboard
    // expect(screen.getByTestId('menu-item-1')).toBeInTheDocument(); // Configure
    expect(screen.getByTestId('menu-item-2')).toBeInTheDocument(); // Metrics
    expect(screen.getByTestId('menu-item-4')).toBeInTheDocument(); // About
  });

  it('renders only allowed menu items for guest user', () => {
    render(
      <TestWrapper userRole="guest">
        <SideBar />
      </TestWrapper>
    );

    // Guest should only see Dashboard, Metrics, and About
    expect(screen.getByTestId('menu-item-0')).toBeInTheDocument(); // Dashboard
    // expect(screen.queryByTestId('menu-item-1')).not.toBeInTheDocument(); // Configure (admin only)
    expect(screen.getByTestId('menu-item-2')).toBeInTheDocument(); // Metrics
    expect(screen.getByTestId('menu-item-5')).toBeInTheDocument(); // About
  });

  it('renders correct NavLinks with proper paths', () => {
    render(
      <TestWrapper userRole="admin">
        <SideBar />
      </TestWrapper>
    );

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(6);

    // Check specific paths
    expect(screen.getByRole('link', { name: /dashboard icon/i })).toHaveAttribute('href', '/');
    // expect(screen.getByRole('link', { name: /configure icon/i })).toHaveAttribute('href', '/configure');
    expect(screen.getByRole('link', { name: /metrics icon/i })).toHaveAttribute('href', '/metrics');
    expect(screen.getByRole('link', { name: /autotier icon/i })).toHaveAttribute('href', '/application_view');
    expect(screen.getByRole('link', { name: /about icon/i })).toHaveAttribute('href', '/about');
  });

  it('applies correct CSS classes to NavLinks', () => {
    render(
      <TestWrapper userRole="admin">
        <SideBar />
      </TestWrapper>
    );

    const links = screen.getAllByRole('link');
    links.forEach(link => {
      expect(link).toHaveClass('link');
    });
  });

  it('renders correct icons for each menu item', () => {
    render(
      <TestWrapper userRole="admin">
        <SideBar />
      </TestWrapper>
    );

    expect(screen.getByTestId('dashboard-icon')).toBeInTheDocument();
    // expect(screen.getByTestId('configure-icon')).toBeInTheDocument();
    expect(screen.getByTestId('metrics-icon')).toBeInTheDocument();
    expect(screen.getByTestId('autotier-icon')).toBeInTheDocument();
    expect(screen.getByTestId('about-icon')).toBeInTheDocument();
  });

  it('renders children prop when provided', () => {
    const TestChild = () => <div data-testid="test-child">Test Child Content</div>;

    render(
      <TestWrapper userRole="admin">
        <SideBar>
          <TestChild />
        </SideBar>
      </TestWrapper>
    );

    expect(screen.getByTestId('test-child')).toBeInTheDocument();
    expect(screen.getByText('Test Child Content')).toBeInTheDocument();
  });

  it('handles unknown user role gracefully', () => {
    render(
      <TestWrapper userRole="unknown">
        <SideBar />
      </TestWrapper>
    );

    // No menu items should be visible for unknown role
    expect(screen.queryByTestId('menu-item-0')).not.toBeInTheDocument();
    expect(screen.queryByTestId('menu-item-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('menu-item-2')).not.toBeInTheDocument();
    expect(screen.queryByTestId('menu-item-3')).not.toBeInTheDocument();
    expect(screen.queryByTestId('menu-item-4')).not.toBeInTheDocument();
  });

  it('maintains correct structure when no menu items are visible', () => {
    render(
      <TestWrapper userRole="unknown">
        <SideBar />
      </TestWrapper>
    );

    const sidebarContainer = screen.getByTestId('sidebar-container');
    expect(sidebarContainer).toBeInTheDocument();

    const sidebar = sidebarContainer.querySelector('.sidebar');
    expect(sidebar).toBeInTheDocument();
    expect(sidebar).toHaveStyle('width: 50px');
  });

  it('filters menu items correctly based on user role permissions', () => {
    const { rerender } = render(
      <TestWrapper userRole="admin">
        <SideBar />
      </TestWrapper>
    );

    // Admin should see 5 items
    expect(screen.getAllByRole('link')).toHaveLength(6);

    // Re-render with guest role
    rerender(
      <TestWrapper userRole="guest">
        <SideBar />
      </TestWrapper>
    );

    // Guest should see 3 items
    expect(screen.getAllByRole('link')).toHaveLength(3);
  });

  it('uses correct test ids for menu items', () => {
    render(
      <TestWrapper userRole="admin">
        <SideBar />
      </TestWrapper>
    );

    // Verify each menu item has the correct data-testid
    const menuItems = ['menu-item-0', 'menu-item-2', 'menu-item-3', 'menu-item-4', 'menu-item-5'];

    menuItems.forEach(testId => {
      expect(screen.getByTestId(testId)).toBeInTheDocument();
      expect(screen.getByTestId(testId)).toHaveClass('icon');
    });
  });
});