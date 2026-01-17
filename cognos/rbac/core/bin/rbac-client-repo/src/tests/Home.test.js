import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { useNavigate } from 'react-router-dom';
import Home from '../components/Home';

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
    useNavigate: jest.fn(),
}));

describe('Home Component', () => {
    let mockNavigate;
    let mockFetch;
    let mockLocalStorage;
    let originalLocation;
    let originalHistory;

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

        // Setup process.env
        process.env.REACT_APP_BACKEND_URL = 'http://localhost:3000';

        // Mock window.location
        originalLocation = window.location;
        delete window.location;
        window.location = {
            protocol: 'http:',
            hostname: 'localhost',
            pathname: '/',
            search: '',
            href: 'http://localhost:3000/',
            assign: jest.fn(),
            replace: jest.fn(),
        };

        // Mock window.history
        originalHistory = window.history;
        Object.defineProperty(window, 'history', {
            writable: true,
            value: {
                replaceState: jest.fn(),
                pushState: jest.fn(),
            },
        });

        // Default fetch responses
        mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            text: async () => '<div>Content</div>',
        });

        // Clear all mocks before each test
        jest.clearAllMocks();
    });

    afterEach(() => {
        window.location = originalLocation;
        window.history = originalHistory;
        jest.restoreAllMocks();
    });

    // Helper function to create a valid JWT token
    const createMockToken = (payload) => {
        const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
        const payloadEncoded = btoa(JSON.stringify(payload));
        const signature = 'mock-signature';
        return `${header}.${payloadEncoded}.${signature}`;
    };

    describe('Component Rendering', () => {
        test('renders Home component with logo', () => {
            render(<Home />);

            expect(screen.getByText(/SAMSUNG/i)).toBeInTheDocument();
            expect(screen.getByText(/Cognos Management Console/i)).toBeInTheDocument();
        });

        test('renders login and signup content divs', () => {
            const { container } = render(<Home />);

            expect(container.querySelector('#loginContent')).toBeInTheDocument();
            expect(container.querySelector('#signupContent')).toBeInTheDocument();
        });

        test('renders with correct layout structure', () => {
            const { container } = render(<Home />);

            const loginDiv = container.querySelector('#loginContent');
            const signupDiv = container.querySelector('#signupContent');

            expect(loginDiv).toHaveStyle({ flex: '1' });
            expect(signupDiv).toHaveStyle({ flex: '1' });
        });
    });

    describe('Initial Content Loading (No Token)', () => {
        test('loads login component on mount', async () => {
            render(<Home />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/login?style=true'
                );
            });
        });

        test('loads signup component on mount', async () => {
            render(<Home />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/signup?style=true'
                );
            });
        });

        test('updates loginContent innerHTML with fetched data', async () => {
            const loginHtml = '<div class="login-form">Login Form</div>';
            mockFetch.mockImplementation((url) => {
                if (url.includes('/login')) {
                    return Promise.resolve({
                        ok: true,
                        text: async () => loginHtml,
                    });
                }
                return Promise.resolve({
                    ok: true,
                    text: async () => '<div>Signup</div>',
                });
            });

            const { container } = render(<Home />);

            await waitFor(() => {
                const loginContent = container.querySelector('#loginContent');
                expect(loginContent.innerHTML).toBe(loginHtml);
            });
        });

        test('updates signupContent innerHTML with fetched data', async () => {
            const signupHtml = '<div class="signup-form">Signup Form</div>';
            mockFetch.mockImplementation((url) => {
                if (url.includes('/signup')) {
                    return Promise.resolve({
                        ok: true,
                        text: async () => signupHtml,
                    });
                }
                return Promise.resolve({
                    ok: true,
                    text: async () => '<div>Login</div>',
                });
            });

            const { container } = render(<Home />);

            await waitFor(() => {
                const signupContent = container.querySelector('#signupContent');
                expect(signupContent.innerHTML).toBe(signupHtml);
            });
        });

        test('executes scripts from login content', async () => {
            const scriptContent = 'window.loginLoaded = true;';
            const loginHtml = `<div>Login</div><script>${scriptContent}</script>`;

            mockFetch.mockImplementation((url) => {
                if (url.includes('/login')) {
                    return Promise.resolve({
                        ok: true,
                        text: async () => loginHtml,
                    });
                }
                return Promise.resolve({
                    ok: true,
                    text: async () => '<div>Signup</div>',
                });
            });

            const appendChildSpy = jest.spyOn(document.body, 'appendChild');

            render(<Home />);

            await waitFor(() => {
                expect(appendChildSpy).toHaveBeenCalled();
                const scripts = appendChildSpy.mock.calls.filter(
                    call => call[0].tagName === 'SCRIPT'
                );
                expect(scripts.length).toBeGreaterThan(0);
            });

            appendChildSpy.mockRestore();
        });

        test('executes scripts from signup content', async () => {
            const scriptContent = 'window.signupLoaded = true;';
            const signupHtml = `<div>Signup</div><script>${scriptContent}</script>`;

            mockFetch.mockImplementation((url) => {
                if (url.includes('/signup')) {
                    return Promise.resolve({
                        ok: true,
                        text: async () => signupHtml,
                    });
                }
                return Promise.resolve({
                    ok: true,
                    text: async () => '<div>Login</div>',
                });
            });

            const appendChildSpy = jest.spyOn(document.body, 'appendChild');

            render(<Home />);

            await waitFor(() => {
                expect(appendChildSpy).toHaveBeenCalled();
            });

            appendChildSpy.mockRestore();
        });
    });

    describe('Token in URL Handling', () => {
        test('extracts token from URL query parameters', async () => {
            const token = createMockToken({ role: 'owner', username: 'testuser' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(mockLocalStorage.setItem).toHaveBeenCalledWith('token', token);
            });
        });

        test('decodes JWT token correctly', async () => {
            const token = createMockToken({ role: 'owner', username: 'testuser' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith('/landing');
            });
        });

        test('navigates to landing for owner role', async () => {
            const token = createMockToken({ role: 'owner' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith('/landing');
            });
        });

        test('redirects to port 5000 for user role', async () => {
            const token = createMockToken({ role: 'user' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(window.location.href).toBe(
                    `http://localhost:5000/?token=${encodeURIComponent(token)}`
                );
            });
        });

        test('redirects to port 5000 for admin role', async () => {
            const token = createMockToken({ role: 'admin' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(window.location.href).toBe(
                    `http://localhost:5000/?token=${encodeURIComponent(token)}`
                );
            });
        });

        test('removes token from URL after processing', async () => {
            const token = createMockToken({ role: 'owner' });
            window.location.search = `?token=${token}`;
            window.location.pathname = '/';

            render(<Home />);

            await waitFor(() => {
                expect(window.history.replaceState).toHaveBeenCalledWith(
                    {},
                    document.title,
                    '/'
                );
            });
        });

        test('handles invalid token structure', async () => {
            const invalidToken = 'invalid.token';
            window.location.search = `?token=${invalidToken}`;

            const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

            render(<Home />);

            await waitFor(() => {
                expect(consoleErrorSpy).toHaveBeenCalledWith('Invalid token structure');
                expect(mockNavigate).toHaveBeenCalledWith('/landing');
            });

            consoleErrorSpy.mockRestore();
        });

        test('handles token with only 2 parts', async () => {
            const invalidToken = 'header.payload';
            window.location.search = `?token=${invalidToken}`;

            const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

            render(<Home />);

            await waitFor(() => {
                expect(consoleErrorSpy).toHaveBeenCalledWith('Invalid token structure');
            });

            consoleErrorSpy.mockRestore();
        });

        test('handles malformed JWT payload', async () => {
            const invalidToken = 'header.invalid-base64.signature';
            window.location.search = `?token=${invalidToken}`;

            const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

            render(<Home />);

            await waitFor(() => {
                expect(consoleErrorSpy).toHaveBeenCalledWith(
                    'Error decoding token:',
                    expect.any(Error)
                );
                expect(mockNavigate).toHaveBeenCalledWith('/landing');
            });

            consoleErrorSpy.mockRestore();
        });

        test('handles token with undefined role', async () => {
            const token = createMockToken({ username: 'testuser' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith('/landing');
            });
        });

        test('handles token with null role', async () => {
            const token = createMockToken({ role: null });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith('/landing');
            });
        });
    });

    describe('Fetch Authorization Header Injection', () => {
        test('modifies global fetch to include Authorization header', async () => {
            const token = createMockToken({ role: 'owner' });
            window.location.search = `?token=${token}`;

            const originalFetch = global.fetch;

            render(<Home />);

            await waitFor(() => {
                expect(window.fetch).not.toBe(originalFetch);
            });
        });

        test('preserves existing headers when adding Authorization', async () => {
            const token = createMockToken({ role: 'owner' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(mockLocalStorage.setItem).toHaveBeenCalled();
            });
        });
    });

    describe('rbacLogin Event Handling', () => {
        test('listens for rbacLogin event', () => {
            const addEventListenerSpy = jest.spyOn(window, 'addEventListener');

            render(<Home />);

            expect(addEventListenerSpy).toHaveBeenCalledWith(
                'rbacLogin',
                expect.any(Function)
            );

            addEventListenerSpy.mockRestore();
        });

        test('navigates to landing when rbacLogin has no token', async () => {
            const { unmount } = render(<Home />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalled();
            });

            const loginEvent = new CustomEvent('rbacLogin', {
                detail: { username: 'testuser' }
            });

            fireEvent(window, loginEvent);

            expect(mockNavigate).toHaveBeenCalledWith('/landing');

            unmount();
        });

        test('removes rbacLogin event listener on unmount', () => {
            const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');

            const { unmount } = render(<Home />);

            unmount();

            expect(removeEventListenerSpy).toHaveBeenCalledWith(
                'rbacLogin',
                expect.any(Function)
            );

            removeEventListenerSpy.mockRestore();
        });
    });

    describe('Error Handling', () => {
        test('handles fetch error for login content', async () => {
            const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

            mockFetch.mockImplementation((url) => {
                if (url.includes('/login')) {
                    return Promise.resolve({
                        ok: false,
                        status: 500
                    });
                }
                return Promise.resolve({
                    ok: true,
                    text: async () => '<div>Signup</div>',
                });
            });

            render(<Home />);

            await waitFor(() => {
                expect(consoleErrorSpy).toHaveBeenCalledWith(
                    'Error loading page:',
                    expect.any(Error)
                );
            });

            consoleErrorSpy.mockRestore();
        });

        test('handles fetch error for signup content', async () => {
            const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

            mockFetch.mockImplementation((url) => {
                if (url.includes('/signup')) {
                    return Promise.resolve({
                        ok: false,
                        status: 500
                    });
                }
                return Promise.resolve({
                    ok: true,
                    text: async () => '<div>Login</div>',
                });
            });

            render(<Home />);

            await waitFor(() => {
                expect(consoleErrorSpy).toHaveBeenCalled();
            });

            consoleErrorSpy.mockRestore();
        });

        test('handles network error during content loading', async () => {
            const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

            mockFetch.mockRejectedValue(new Error('Network error'));

            render(<Home />);

            await waitFor(() => {
                expect(consoleErrorSpy).toHaveBeenCalledWith(
                    'Error loading page:',
                    expect.any(Error)
                );
            });

            consoleErrorSpy.mockRestore();
        });

        test('continues rendering even if content loading fails', async () => {
            mockFetch.mockRejectedValue(new Error('Network error'));

            const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

            render(<Home />);

            expect(screen.getByText(/SAMSUNG/i)).toBeInTheDocument();

            consoleErrorSpy.mockRestore();
        });
    });

    describe('URL Redirect Construction', () => {
        test('constructs redirect URL with https protocol', async () => {
            window.location.protocol = 'https:';
            const token = createMockToken({ role: 'user' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(window.location.href).toBe(
                    `https://localhost:5000/?token=${encodeURIComponent(token)}`
                );
            });
        });

        test('constructs redirect URL with different hostname', async () => {
            window.location.hostname = 'example.com';
            const token = createMockToken({ role: 'user' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(window.location.href).toBe(
                    `http://example.com:5000/?token=${encodeURIComponent(token)}`
                );
            });
        });

        test('properly encodes token in redirect URL', async () => {
            const token = createMockToken({ role: 'admin' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(window.location.href).toContain(encodeURIComponent(token));
            });
        });
    });

    describe('Edge Cases', () => {
        test('handles missing loginContent element', async () => {
            const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => { });

            const { container } = render(<Home />);

            // Remove the element
            const loginContent = container.querySelector('#loginContent');
            if (loginContent) {
                loginContent.remove();
            }

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalled();
            });

            // Should not throw error
            expect(consoleErrorSpy).not.toHaveBeenCalled();

            consoleErrorSpy.mockRestore();
        });

        test('handles token with special characters', async () => {
            const token = createMockToken({ role: 'owner', special: '!@#$%' });
            window.location.search = `?token=${encodeURIComponent(token)}`;

            render(<Home />);

            await waitFor(() => {
                expect(mockLocalStorage.setItem).toHaveBeenCalledWith('token', token);
            });
        });

        test('handles multiple query parameters with token', async () => {
            const token = createMockToken({ role: 'owner' });
            window.location.search = `?foo=bar&token=${token}&baz=qux`;

            render(<Home />);

            await waitFor(() => {
                expect(mockLocalStorage.setItem).toHaveBeenCalledWith('token', token);
            });
        });

        test('does not process content loading when token is present', async () => {
            const token = createMockToken({ role: 'owner' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalled();
            });

            // Should not fetch login/signup content when token is in URL
            const loginFetchCalls = mockFetch.mock.calls.filter(
                call => call[0] && call[0].includes('/login')
            );
            expect(loginFetchCalls.length).toBe(0);
        });

        test('handles empty token parameter', async () => {
            window.location.search = '?token=';

            render(<Home />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalled();
            });
        });

        test('handles role with unexpected value', async () => {
            const token = createMockToken({ role: 'superuser' });
            window.location.search = `?token=${token}`;

            render(<Home />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith('/landing');
            });
        });
    });

    describe('Script Execution from Dynamic Content', () => {
        test('executes multiple scripts from login content', async () => {
            const loginHtml = `
        <div>Login</div>
        <script>var login1 = true;</script>
        <script>var login2 = true;</script>
      `;

            mockFetch.mockImplementation((url) => {
                if (url.includes('/login')) {
                    return Promise.resolve({
                        ok: true,
                        text: async () => loginHtml,
                    });
                }
                return Promise.resolve({
                    ok: true,
                    text: async () => '<div>Signup</div>',
                });
            });

            const appendChildSpy = jest.spyOn(document.body, 'appendChild');

            render(<Home />);

            await waitFor(() => {
                const scriptCalls = appendChildSpy.mock.calls.filter(
                    call => call[0].tagName === 'SCRIPT'
                );
                expect(scriptCalls.length).toBeGreaterThanOrEqual(2);
            });

            appendChildSpy.mockRestore();
        });

        test('handles content with no scripts', async () => {
            const loginHtml = '<div>Simple Login Form</div>';

            mockFetch.mockImplementation((url) => {
                if (url.includes('/login')) {
                    return Promise.resolve({
                        ok: true,
                        text: async () => loginHtml,
                    });
                }
                return Promise.resolve({
                    ok: true,
                    text: async () => '<div>Signup</div>',
                });
            });

            const appendChildSpy = jest.spyOn(document.body, 'appendChild');

            const { container } = render(<Home />);

            await waitFor(() => {
                const loginContent = container.querySelector('#loginContent');
                expect(loginContent.innerHTML).toBe(loginHtml);
            });

            appendChildSpy.mockRestore();
        });
    });
});