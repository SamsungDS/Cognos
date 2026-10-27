import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { useNavigate } from 'react-router-dom';
import Dashboard from '../components/Dashboard';

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
    useNavigate: jest.fn(),
}));

describe('Dashboard Component', () => {
    let mockNavigate;
    let mockFetch;
    let mockLocalStorage;

    beforeEach(() => {
        // Setup navigate mock
        mockNavigate = jest.fn();
        useNavigate.mockReturnValue(mockNavigate);

        // Setup fetch mock
        mockFetch = jest.fn();
        global.fetch = mockFetch;

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

        // Setup alert mock
        global.alert = jest.fn();

        // Setup process.env
        process.env.REACT_APP_BACKEND_URL = 'http://localhost:3000';

        // Clear all mocks before each test
        jest.clearAllMocks();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    describe('Component Rendering', () => {
        test('renders Dashboard component with back button', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Dashboard Content</div>',
            });

            render(<Dashboard />);

            const backButton = screen.getByRole('button', { name: /back to landing page/i });
            expect(backButton).toBeInTheDocument();
        });

        test('renders dashboardContent div', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Dashboard Content</div>',
            });

            const { container } = render(<Dashboard />);

            const dashboardContent = container.querySelector('#dashboardContent');
            expect(dashboardContent).toBeInTheDocument();
        });
    });

    describe('Token Validation', () => {
        test('redirects to home when no token is found', async () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<Dashboard />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('No token found, please log in.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('checks localStorage for token on mount', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Content</div>',
            });

            render(<Dashboard />);

            expect(mockLocalStorage.getItem).toHaveBeenCalledWith('token');
        });
    });

    describe('API Calls', () => {
        test('makes fetch request with correct URL and headers when token exists', async () => {
            const token = 'test-token-123';
            mockLocalStorage.getItem.mockReturnValue(token);
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Dashboard Content</div>',
            });

            render(<Dashboard />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/dashboard?style=true',
                    {
                        headers: { Authorization: `Bearer ${token}` }
                    }
                );
            });
        });

        test('handles successful API response and updates DOM', async () => {
            const htmlContent = '<div class="dashboard-data">Test Content</div>';
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => htmlContent,
            });

            const { container } = render(<Dashboard />);

            await waitFor(() => {
                const dashboardContent = container.querySelector('#dashboardContent');
                expect(dashboardContent.innerHTML).toBe(htmlContent);
            });
        });

        test('handles API response with status not ok', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: false,
                status: 401,
            });

            render(<Dashboard />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /dashboard page. Redirecting to home.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('handles network error during fetch', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockRejectedValue(new Error('Network error'));

            render(<Dashboard />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /dashboard page. Redirecting to home.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });
    });

    describe('Navigation', () => {
        test('navigates to landing page when back button is clicked', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Content</div>',
            });

            render(<Dashboard />);

            const backButton = screen.getByRole('button', { name: /back to landing page/i });
            fireEvent.click(backButton);

            expect(mockNavigate).toHaveBeenCalledWith('/landing');
        });
    });

    describe('useEffect Dependencies', () => {
        test('runs useEffect only once on mount with navigate dependency', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Content</div>',
            });

            const { rerender } = render(<Dashboard />);

            expect(mockFetch).toHaveBeenCalledTimes(1);

            // Rerender with same navigate function
            rerender(<Dashboard />);

            // Should still be called only once
            expect(mockFetch).toHaveBeenCalledTimes(1);
        });
    });
});