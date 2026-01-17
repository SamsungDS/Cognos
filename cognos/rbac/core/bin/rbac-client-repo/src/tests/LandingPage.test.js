import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useNavigate } from 'react-router-dom';
import LandingPage from '../components/LandingPage';

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
    useNavigate: jest.fn(),
}));

describe('LandingPage Component', () => {
    let mockNavigate;
    let mockLocalStorage;
    let consoleErrorSpy;

    beforeEach(() => {
        // Setup navigate mock
        mockNavigate = jest.fn();
        useNavigate.mockReturnValue(mockNavigate);

        // Setup localStorage mock
        mockLocalStorage = {
            getItem: jest.fn(),
            setItem: jest.fn(),
            removeItem: jest.fn(),
            clear: jest.fn(),
        };
        Object.defineProperty(window, 'localStorage', {
            value: mockLocalStorage,
            writable: true,
        });

        // Mock console.error
        consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

        // Clear all mocks before each test
        jest.clearAllMocks();
    });

    afterEach(() => {
        consoleErrorSpy.mockRestore();
    });

    // Helper function to create a valid JWT token
    const createMockToken = (payload) => {
        const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
        const payloadEncoded = btoa(JSON.stringify(payload));
        const signature = 'mock-signature';
        return `${header}.${payloadEncoded}.${signature}`;
    };

    describe('Component Rendering', () => {
        test('renders LandingPage component with title', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            expect(screen.getByText('Welcome to RBAC System')).toBeInTheDocument();
        });

        test('renders all basic navigation buttons', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            expect(screen.getByText(/Profile/i)).toBeInTheDocument();
            expect(screen.getByText(/User Management/i)).toBeInTheDocument();
            expect(screen.getByText(/Settings/i)).toBeInTheDocument();
            expect(screen.getByText(/Logout/i)).toBeInTheDocument();
        });

        test('renders welcome message with empty username and role when no token', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            expect(screen.getByText(/Hello,/i)).toBeInTheDocument();
            expect(screen.getByText(/\(\)/i)).toBeInTheDocument();
        });
    });

    describe('Token Decoding and User Information', () => {
        test('decodes valid JWT token and sets user role and username', () => {
            const token = createMockToken({
                role: 'admin',
                username: 'testuser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            expect(screen.getByText(/testuser/i)).toBeInTheDocument();
            expect(screen.getByText(/admin/i)).toBeInTheDocument();
        });

        test('handles missing token gracefully', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            expect(mockLocalStorage.getItem).toHaveBeenCalledWith('token');
            expect(screen.getByText(/Hello,/i)).toBeInTheDocument();
        });

        test('handles invalid token format', () => {
            mockLocalStorage.getItem.mockReturnValue('invalid-token');

            render(<LandingPage />);

            expect(consoleErrorSpy).toHaveBeenCalledWith(
                'Error decoding token:',
                expect.any(Error)
            );
        });

        test('handles malformed JWT token', () => {
            mockLocalStorage.getItem.mockReturnValue('header.invalid-payload.signature');

            render(<LandingPage />);

            expect(consoleErrorSpy).toHaveBeenCalled();
        });

        test('handles token with missing payload', () => {
            mockLocalStorage.getItem.mockReturnValue('header..signature');

            render(<LandingPage />);

            expect(consoleErrorSpy).toHaveBeenCalled();
        });
    });

    describe('Role-Based Rendering', () => {
        test('shows User Management button only for owner role', () => {
            const token = createMockToken({
                role: 'owner',
                username: 'owneruser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            expect(screen.getByText(/Approvals/i)).toBeInTheDocument();
        });

        test('does not show User Management button for admin role', () => {
            const token = createMockToken({
                role: 'admin',
                username: 'adminuser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            expect(screen.queryByText(/Approvals/i)).not.toBeInTheDocument();
        });

        test('does not show User Management button for user role', () => {
            const token = createMockToken({
                role: 'user',
                username: 'regularuser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            expect(screen.queryByText(/Approvals/i)).not.toBeInTheDocument();
        });

        test('does not show User Management button when no token', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            expect(screen.queryByText(/Approvals/i)).not.toBeInTheDocument();
        });
    });

    describe('Navigation Functionality', () => {
        test('navigates to profile when Profile button is clicked', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            const profileButton = screen.getByText(/Profile/i);
            fireEvent.click(profileButton);

            expect(mockNavigate).toHaveBeenCalledWith('/profile');
        });

        test('navigates to dashboard when Dashboard button is clicked', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            const dashboardButton = screen.getByText(/User Management/i);
            fireEvent.click(dashboardButton);

            expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
        });

        test('navigates to settings when Settings button is clicked', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            const settingsButton = screen.getByText(/Settings/i);
            fireEvent.click(settingsButton);

            expect(mockNavigate).toHaveBeenCalledWith('/settings');
        });

        test('navigates to user-approval when User Management button is clicked (owner only)', () => {
            const token = createMockToken({
                role: 'owner',
                username: 'owneruser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            const userManagementButton = screen.getByText(/Approvals/i);
            fireEvent.click(userManagementButton);

            expect(mockNavigate).toHaveBeenCalledWith('/user-approval');
        });
    });

    describe('Logout Functionality', () => {
        test('removes token from localStorage when logout is clicked', () => {
            const token = createMockToken({
                role: 'user',
                username: 'testuser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            const logoutButton = screen.getByText(/Logout/i);
            fireEvent.click(logoutButton);

            expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('token');
        });

        test('navigates to home page when logout is clicked', () => {
            const token = createMockToken({
                role: 'user',
                username: 'testuser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            const logoutButton = screen.getByText(/Logout/i);
            fireEvent.click(logoutButton);

            expect(mockNavigate).toHaveBeenCalledWith('/');
        });

        test('logout works when no token exists', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            const logoutButton = screen.getByText(/Logout/i);
            fireEvent.click(logoutButton);

            expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('token');
            expect(mockNavigate).toHaveBeenCalledWith('/');
        });
    });

    describe('Button Hover Effects', () => {
        test('Profile button changes color on mouse over and out', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            const profileButton = screen.getByText(/Profile/i);

            // Initial color
            expect(profileButton.style.backgroundColor).toBe('rgb(0, 123, 255)');

            // Mouse over
            fireEvent.mouseOver(profileButton);
            expect(profileButton.style.backgroundColor).toBe('rgb(0, 86, 179)');

            // Mouse out
            fireEvent.mouseOut(profileButton);
            expect(profileButton.style.backgroundColor).toBe('rgb(0, 123, 255)');
        });

        test('Dashboard button changes color on mouse over and out', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            const dashboardButton = screen.getByText(/User Management/i);

            expect(dashboardButton.style.backgroundColor).toBe('rgb(40, 167, 69)');

            fireEvent.mouseOver(dashboardButton);
            expect(dashboardButton.style.backgroundColor).toBe('rgb(30, 126, 52)');

            fireEvent.mouseOut(dashboardButton);
            expect(dashboardButton.style.backgroundColor).toBe('rgb(40, 167, 69)');
        });

        test('Settings button changes color on mouse over and out', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            const settingsButton = screen.getByText(/Settings/i);

            expect(settingsButton.style.backgroundColor).toBe('rgb(108, 117, 125)');

            fireEvent.mouseOver(settingsButton);
            expect(settingsButton.style.backgroundColor).toBe('rgb(84, 91, 98)');

            fireEvent.mouseOut(settingsButton);
            expect(settingsButton.style.backgroundColor).toBe('rgb(108, 117, 125)');
        });

        test('Logout button changes color on mouse over and out', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            const logoutButton = screen.getByText(/Logout/i);

            expect(logoutButton.style.backgroundColor).toBe('rgb(220, 53, 69)');

            fireEvent.mouseOver(logoutButton);
            expect(logoutButton.style.backgroundColor).toBe('rgb(200, 35, 51)');

            fireEvent.mouseOut(logoutButton);
            expect(logoutButton.style.backgroundColor).toBe('rgb(220, 53, 69)');
        });

        test('User Management button changes color on mouse over and out (owner only)', () => {
            const token = createMockToken({
                role: 'owner',
                username: 'owneruser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            const userManagementButton = screen.getByText(/Approvals/i);

            expect(userManagementButton.style.backgroundColor).toBe('rgb(253, 126, 20)');

            fireEvent.mouseOver(userManagementButton);
            expect(userManagementButton.style.backgroundColor).toBe('rgb(232, 99, 13)');

            fireEvent.mouseOut(userManagementButton);
            expect(userManagementButton.style.backgroundColor).toBe('rgb(253, 126, 20)');
        });
    });

    describe('useEffect Dependencies', () => {
        test('useEffect runs only once on mount', () => {
            const token = createMockToken({
                role: 'user',
                username: 'testuser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            const { rerender } = render(<LandingPage />);

            expect(mockLocalStorage.getItem).toHaveBeenCalledTimes(1);

            // Rerender component
            rerender(<LandingPage />);

            // Should still be called only once
            expect(mockLocalStorage.getItem).toHaveBeenCalledTimes(1);
        });
    });

    describe('Edge Cases', () => {
        test('handles token with special characters in username', () => {
            const token = createMockToken({
                role: 'user',
                username: 'test@user.com'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            expect(screen.getByText(/test@user\.com/i)).toBeInTheDocument();
        });

        test('handles token with numeric username', () => {
            const token = createMockToken({
                role: 'admin',
                username: '12345'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            expect(screen.getByText(/12345/i)).toBeInTheDocument();
        });

        test('handles token with empty string username', () => {
            const token = createMockToken({
                role: 'user',
                username: ''
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            expect(screen.getByText(/Hello,/i)).toBeInTheDocument();
        });

        test('handles token with undefined role', () => {
            const token = createMockToken({
                username: 'testuser'
            });
            mockLocalStorage.getItem.mockReturnValue(token);

            render(<LandingPage />);

            expect(screen.getByText(/testuser/i)).toBeInTheDocument();
            // User Management button should not appear with undefined role
            expect(screen.queryByText(/Approvals/i)).not.toBeInTheDocument();
        });

        test('handles multiple consecutive logout clicks', () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<LandingPage />);

            const logoutButton = screen.getByText(/Logout/i);

            fireEvent.click(logoutButton);
            fireEvent.click(logoutButton);
            fireEvent.click(logoutButton);

            expect(mockLocalStorage.removeItem).toHaveBeenCalledTimes(3);
            expect(mockNavigate).toHaveBeenCalledTimes(3);
        });
    });
});