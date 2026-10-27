import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { useNavigate } from 'react-router-dom';
import Settings from '../components/Settings';

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
    useNavigate: jest.fn(),
}));

describe('Settings Component', () => {
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
        test('renders Settings component with back button', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Settings Content</div>',
            });

            render(<Settings />);

            const backButton = screen.getByRole('button', { name: /back to landing page/i });
            expect(backButton).toBeInTheDocument();
        });

        test('renders settingContent div', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Settings Content</div>',
            });

            const { container } = render(<Settings />);

            const settingContent = container.querySelector('#settingContent');
            expect(settingContent).toBeInTheDocument();
        });

        test('renders component structure correctly', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Settings Content</div>',
            });

            const { container } = render(<Settings />);

            expect(container.querySelector('div')).toBeInTheDocument();
            expect(screen.getByRole('button')).toBeInTheDocument();
            expect(container.querySelector('#settingContent')).toBeInTheDocument();
        });
    });

    describe('Token Validation', () => {
        test('redirects to home when no token is found', async () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<Settings />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('No token found, please log in.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('redirects to home when token is empty string', async () => {
            mockLocalStorage.getItem.mockReturnValue('');

            render(<Settings />);

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

            render(<Settings />);

            expect(mockLocalStorage.getItem).toHaveBeenCalledWith('token');
        });

        test('does not make API call when token is missing', async () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<Settings />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });

            expect(mockFetch).not.toHaveBeenCalled();
        });
    });

    describe('API Calls', () => {
        test('makes fetch request with correct URL and headers when token exists', async () => {
            const token = 'test-token-123';
            mockLocalStorage.getItem.mockReturnValue(token);
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Settings Content</div>',
            });

            render(<Settings />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/settings?style=true',
                    {
                        headers: { Authorization: `Bearer ${token}` }
                    }
                );
            });
        });

        test('handles successful API response and updates DOM', async () => {
            const htmlContent = '<div class="settings-data">User Settings Data</div>';
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => htmlContent,
            });

            const { container } = render(<Settings />);

            await waitFor(() => {
                const settingContent = container.querySelector('#settingContent');
                expect(settingContent.innerHTML).toBe(htmlContent);
            });
        });

        test('handles API response with 401 status', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: false,
                status: 401,
            });

            render(<Settings />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /settings page. Redirecting to home.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('handles API response with 403 status', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: false,
                status: 403,
            });

            render(<Settings />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /settings page. Redirecting to home.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('handles API response with 404 status', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: false,
                status: 404,
            });

            render(<Settings />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /settings page. Redirecting to home.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('handles API response with 500 status', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: false,
                status: 500,
            });

            render(<Settings />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /settings page. Redirecting to home.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('handles network error during fetch', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockRejectedValue(new Error('Network error'));

            render(<Settings />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /settings page. Redirecting to home.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('handles timeout error', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockRejectedValue(new Error('Request timeout'));

            render(<Settings />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /settings page. Redirecting to home.');
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

            render(<Settings />);

            const backButton = screen.getByRole('button', { name: /back to landing page/i });
            fireEvent.click(backButton);

            expect(mockNavigate).toHaveBeenCalledWith('/landing');
        });

        test('back button is clickable before content loads', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockImplementation(() => new Promise(resolve => {
                setTimeout(() => resolve({
                    ok: true,
                    text: async () => '<div>Content</div>',
                }), 1000);
            }));

            render(<Settings />);

            const backButton = screen.getByRole('button', { name: /back to landing page/i });
            fireEvent.click(backButton);

            expect(mockNavigate).toHaveBeenCalledWith('/landing');
        });

        test('back button works multiple times', () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Content</div>',
            });

            render(<Settings />);

            const backButton = screen.getByRole('button', { name: /back to landing page/i });

            fireEvent.click(backButton);
            fireEvent.click(backButton);
            fireEvent.click(backButton);

            expect(mockNavigate).toHaveBeenCalledTimes(3);
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

            const { rerender } = render(<Settings />);

            expect(mockFetch).toHaveBeenCalledTimes(1);

            // Rerender with same navigate function
            rerender(<Settings />);

            // Should still be called only once
            expect(mockFetch).toHaveBeenCalledTimes(1);
        });

        test('does not call API again on rerender', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Content</div>',
            });

            const { rerender } = render(<Settings />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledTimes(1);
            });

            rerender(<Settings />);

            expect(mockFetch).toHaveBeenCalledTimes(1);
        });
    });

    describe('DOM Manipulation', () => {
        test('updates innerHTML of settingContent element', async () => {
            const content = '<h1>User Settings</h1><p>Theme: Dark Mode</p>';
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => content,
            });

            const { container } = render(<Settings />);

            await waitFor(() => {
                const settingContent = container.querySelector('#settingContent');
                expect(settingContent.innerHTML).toBe(content);
            });
        });

        test('handles complex HTML content', async () => {
            const content = `
        <div class="settings-header">
          <h1>Settings</h1>
        </div>
        <div class="settings-body">
          <form>
            <label>Theme:</label>
            <select><option>Light</option><option>Dark</option></select>
          </form>
        </div>
      `;
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => content,
            });

            const { container } = render(<Settings />);

            await waitFor(() => {
                const settingContent = container.querySelector('#settingContent');
                expect(settingContent.innerHTML).toBe(content);
            });
        });

        test('handles HTML with inline styles', async () => {
            const content = '<div style="background: #f0f0f0; padding: 20px;">Styled Settings</div>';
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => content,
            });

            const { container } = render(<Settings />);

            await waitFor(() => {
                const settingContent = container.querySelector('#settingContent');
                expect(settingContent.innerHTML).toBe(content);
            });
        });
    });

    describe('Edge Cases', () => {
        test('handles empty response from API', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '',
            });

            const { container } = render(<Settings />);

            await waitFor(() => {
                const settingContent = container.querySelector('#settingContent');
                expect(settingContent.innerHTML).toBe('');
            });
        });

        test('handles very long token', async () => {
            const longToken = 'a'.repeat(1000);
            mockLocalStorage.getItem.mockReturnValue(longToken);
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Content</div>',
            });

            render(<Settings />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/settings?style=true',
                    {
                        headers: { Authorization: `Bearer ${longToken}` }
                    }
                );
            });
        });

        test('handles special characters in token', async () => {
            const specialToken = 'token-with-special-chars!@#$%';
            mockLocalStorage.getItem.mockReturnValue(specialToken);
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '<div>Content</div>',
            });

            render(<Settings />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/settings?style=true',
                    {
                        headers: { Authorization: `Bearer ${specialToken}` }
                    }
                );
            });
        });

        test('handles response with only whitespace', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: true,
                text: async () => '   ',
            });

            const { container } = render(<Settings />);

            await waitFor(() => {
                const settingContent = container.querySelector('#settingContent');
                expect(settingContent.innerHTML).toBe('   ');
            });
        });

        test('handles concurrent navigation attempts', async () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<Settings />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });

            const backButton = screen.getByRole('button', { name: /back to landing page/i });
            fireEvent.click(backButton);

            expect(mockNavigate).toHaveBeenCalledTimes(2);
        });

    });

    describe('Error Scenarios', () => {
        test('handles TypeError during fetch', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockRejectedValue(new TypeError('Failed to fetch'));

            render(<Settings />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /settings page. Redirecting to home.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('handles AbortError during fetch', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            const abortError = new Error('The operation was aborted');
            abortError.name = 'AbortError';
            mockFetch.mockRejectedValue(abortError);

            render(<Settings />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('does not call navigate multiple times on error', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockRejectedValue(new Error('Network error'));

            render(<Settings />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledTimes(1);
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('handles error when response.ok is false', async () => {
            mockLocalStorage.getItem.mockReturnValue('test-token');
            mockFetch.mockResolvedValue({
                ok: false,
                status: 400,
            });

            render(<Settings />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Error loading /settings page. Redirecting to home.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });
    });
});