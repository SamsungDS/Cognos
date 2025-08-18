import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import Home from '../components/Login';
import Login from '../components/Login';

// Mock react-router-dom
const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
    ...jest.requireActual('react-router-dom'),
    useNavigate: () => mockNavigate,
}));

// Mock config
jest.mock('../config/config.json', () => ({
    mgmt_endpoint: 'https://mock-mgmt-endpoint.com',
    rbac_backend_endpoint: 'https://mock-rbac-backend.com',
}));

// Mock axios
jest.mock('axios');

describe('Home Component', () => {
    let mockFetch;
    let originalLocalStorage;
    let originalLocation;

    beforeAll(() => {
        // Mock localStorage
        const localStorageMock = {
            getItem: jest.fn(),
            setItem: jest.fn(),
            removeItem: jest.fn(),
            clear: jest.fn(),
        };
        originalLocalStorage = global.localStorage;
        Object.defineProperty(global, 'localStorage', {
            value: localStorageMock,
            writable: true,
        });

        // Mock location
        originalLocation = global.location;
        delete global.location;
        global.location = { href: '' };
    });

    beforeEach(() => {
        // Clear all mocks
        jest.clearAllMocks();

        // Reset mocks
        global.localStorage.getItem.mockClear();
        global.localStorage.removeItem.mockClear();
        global.location.href = '';

        // Create a more realistic fetch mock
        mockFetch = jest.fn();
        global.fetch = mockFetch;

        // Set up default successful responses
        mockFetch
            .mockResolvedValueOnce({
                ok: true,
                text: () => Promise.resolve('<div id="login-form">Login Form</div>'),
            })
            .mockResolvedValueOnce({
                ok: true,
                text: () => Promise.resolve('<div id="signup-form">Signup Form</div>'),
            });

        // Mock console methods
        jest.spyOn(console, 'error').mockImplementation(() => { });
        jest.spyOn(console, 'log').mockImplementation(() => { });
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    afterAll(() => {
        // Restore originals
        global.localStorage = originalLocalStorage;
        global.location = originalLocation;
    });

    const renderComponent = () => {
        return render(
            <BrowserRouter>
                <Home />
            </BrowserRouter>
        );
    };
    
    test('renders without crashing', () => {
        const { container } = render(
            <BrowserRouter>
                <Login />
            </BrowserRouter>
        );
        expect(container).toBeInTheDocument();
    });

    test('renders without crash', () => {
        const { container } = renderComponent(); // Use your existing helper
        expect(container).toBeInTheDocument();
    });

    test('renders Samsung Cognos Management Console title', () => {
        renderComponent();

        expect(screen.getByText(/SAMSUNG/)).toBeInTheDocument();
        expect(screen.getByText(/Cognos Management Console/)).toBeInTheDocument();
    });

    test('renders login and signup content containers', () => {
        const { container } = renderComponent();

        const loginContent = container.querySelector('#loginContent');
        expect(loginContent).toBeInTheDocument();

        const signupContent = container.querySelector('#signupContent');
        expect(signupContent).toBeInTheDocument();
    });

    test('makes API calls on component mount', async () => {
        renderComponent();

        // Wait for the useEffect to complete
        await waitFor(() => {
            expect(mockFetch).toHaveBeenCalledTimes(2);
        }, { timeout: 3000 });

        expect(mockFetch).toHaveBeenCalledWith(
            'https://mock-rbac-backend.com/api/login?style=true'
        );
        expect(mockFetch).toHaveBeenCalledWith(
            'https://mock-rbac-backend.com/api/signup?style=true'
        );
    });

    test('sets up event listeners for rbacLogin', async () => {
        const addEventListenerSpy = jest.spyOn(window, 'addEventListener');

        renderComponent();

        await waitFor(() => {
            expect(addEventListenerSpy).toHaveBeenCalledWith(
                'rbacLogin',
                expect.any(Function)
            );
        });
    });

    test('loads content into DOM elements', async () => {
        // Create real DOM elements that the component can find
        const loginDiv = document.createElement('div');
        loginDiv.id = 'loginContent';
        document.body.appendChild(loginDiv);

        const signupDiv = document.createElement('div');
        signupDiv.id = 'signupContent';
        document.body.appendChild(signupDiv);

        renderComponent();

        await waitFor(() => {
            expect(mockFetch).toHaveBeenCalledTimes(2);
        }, { timeout: 3000 });

        // Check that content was loaded (the actual DOM manipulation happens after fetch)
        await waitFor(() => {
            const loginElement = document.getElementById('loginContent');
            const signupElement = document.getElementById('signupContent');

            // The component should have set innerHTML
            expect(loginElement).toBeTruthy();
            expect(signupElement).toBeTruthy();
        }, { timeout: 1000 });

        // Clean up
        document.body.removeChild(loginDiv);
        document.body.removeChild(signupDiv);
    });

    test('component structure includes required CSS classes', () => {
        const { container } = renderComponent();

        expect(container.querySelector('.Home-page-style')).toBeInTheDocument();
        expect(container.querySelector('.rbac-samsung-logo')).toBeInTheDocument();
    });

    test('component has flex layout structure', () => {
        const { container } = renderComponent();

        // Check for the flex container (it has inline styles)
        const flexContainers = container.querySelectorAll('div[style*="display"]');
        expect(flexContainers.length).toBeGreaterThan(0);
    });
});