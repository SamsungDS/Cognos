import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { useNavigate } from 'react-router-dom';
import UserApproval from '../components/UserApproval';

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
    useNavigate: jest.fn(),
}));

describe('UserApproval Component', () => {
    let mockNavigate;
    let mockFetch;
    let mockLocalStorage;

    const mockPendingUsers = [
        {
            id: 1,
            username: 'pendinguser1',
            email: 'pending1@example.com',
            role: 'user',
            createdAt: '2024-01-15T10:00:00Z',
            is_verified: true,
            is_approved: false
        },
        {
            id: 2,
            username: 'pendinguser2',
            email: 'pending2@example.com',
            role: 'admin',
            createdAt: '2024-01-16T11:00:00Z',
            is_verified: false,
            is_approved: false
        }
    ];

    const mockAllUsers = [
        {
            id: 3,
            username: 'approveduser',
            email: 'approved@example.com',
            role: 'user',
            createdAt: '2024-01-10T09:00:00Z',
            is_verified: true,
            is_approved: true,
            approved_by: 'owner',
            approved_at: '2024-01-11T10:00:00Z'
        },
        {
            id: 4,
            username: 'rejecteduser',
            email: 'rejected@example.com',
            role: 'user',
            createdAt: '2024-01-12T12:00:00Z',
            is_verified: true,
            is_approved: false
        }
    ];

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

        // Default mock responses
        mockLocalStorage.getItem.mockReturnValue('test-token');
        mockFetch.mockImplementation((url) => {
            if (url.includes('/api/pending-users')) {
                return Promise.resolve({
                    ok: true,
                    status: 200,
                    json: async () => ({ users: mockPendingUsers })
                });
            } else if (url.includes('/api/all-users')) {
                return Promise.resolve({
                    ok: true,
                    status: 200,
                    json: async () => ({ users: mockAllUsers })
                });
            }
            return Promise.resolve({ ok: true, json: async () => ({}) });
        });

        // Clear all mocks before each test
        jest.clearAllMocks();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    describe('Component Rendering', () => {
        test('renders UserApproval component with header', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('Approvals')).toBeInTheDocument();
                expect(screen.getByText('Approve or reject user registrations')).toBeInTheDocument();
            });
        });

        test('renders back button', async () => {
            render(<UserApproval />);

            const backButton = screen.getByText(/Back to Landing Page/i);
            expect(backButton).toBeInTheDocument();
        });

        test('renders tabs for pending and all users', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText(/Pending Approvals/i)).toBeInTheDocument();
                expect(screen.getByText(/All Users/i)).toBeInTheDocument();
            });
        });

        test('shows pending tab as active by default', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                const pendingTab = screen.getByText(/Pending Approvals/i).closest('button');
                expect(pendingTab).toHaveClass('active');
            });
        });
    });

    describe('Initial Data Fetching', () => {
        test('fetches pending users on mount', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/pending-users',
                    { headers: { Authorization: 'Bearer test-token' } }
                );
            });
        });

        test('fetches all users on mount', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/all-users',
                    { headers: { Authorization: 'Bearer test-token' } }
                );
            });
        });

        test('displays pending users data', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
                expect(screen.getByText('pending1@example.com')).toBeInTheDocument();
                expect(screen.getByText('pendinguser2')).toBeInTheDocument();
            });
        });

        test('shows loading state initially', () => {
            render(<UserApproval />);

            expect(screen.getByText('Loading...')).toBeInTheDocument();
        });

        test('hides loading state after data is fetched', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
            });
        });
    });

    describe('Token Validation', () => {
        test('redirects to home when no token for pending users', async () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<UserApproval />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('No token found, please log in.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('redirects to home when no token for all users', async () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<UserApproval />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('does not fetch data when token is missing', async () => {
            mockLocalStorage.getItem.mockReturnValue(null);

            render(<UserApproval />);

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalled();
            });

            // Should not make successful fetch calls
            const successfulCalls = mockFetch.mock.calls.filter(call =>
                call[0].includes('/api/pending-users') || call[0].includes('/api/all-users')
            );
            expect(successfulCalls.length).toBe(0);
        });
    });

    describe('Access Control', () => {
        test('redirects when pending users returns 403', async () => {
            mockFetch.mockImplementation((url) => {
                if (url.includes('/api/pending-users')) {
                    return Promise.resolve({
                        ok: false,
                        status: 403,
                        json: async () => ({})
                    });
                }
                return Promise.resolve({
                    ok: true,
                    status: 200,
                    json: async () => ({ users: [] })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Access denied. Owner role required.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });

        test('redirects when all users returns 403', async () => {
            mockFetch.mockImplementation((url) => {
                if (url.includes('/api/all-users')) {
                    return Promise.resolve({
                        ok: false,
                        status: 403,
                        json: async () => ({})
                    });
                }
                return Promise.resolve({
                    ok: true,
                    status: 200,
                    json: async () => ({ users: [] })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('Access denied. Owner role required.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });
    });

    describe('Tab Navigation', () => {
        test('switches to all users tab when clicked', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });

            const allUsersTab = screen.getByText(/All Users/i);
            fireEvent.click(allUsersTab);

            await waitFor(() => {
                expect(screen.getByText('approveduser')).toBeInTheDocument();
            });
        });

        test('switches back to pending tab when clicked', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });

            // Switch to all users
            const allUsersTab = screen.getByText(/All Users/i);
            fireEvent.click(allUsersTab);

            await waitFor(() => {
                expect(screen.getByText('approveduser')).toBeInTheDocument();
            });

            // Switch back to pending
            const pendingTab = screen.getByText(/Pending Approvals/i);
            fireEvent.click(pendingTab);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });
        });

        test('displays correct user count in tab labels', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText(`Pending Approvals (${mockPendingUsers.length})`)).toBeInTheDocument();
                expect(screen.getByText(`All Users (${mockAllUsers.length})`)).toBeInTheDocument();
            });
        });
    });

    describe('User Actions', () => {
        test('approves user successfully', async () => {
            mockFetch.mockImplementation((url, options) => {
                if (url.includes('/api/update-user-approval')) {
                    return Promise.resolve({
                        ok: true,
                        json: async () => ({ message: 'User approved successfully' })
                    });
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: mockPendingUsers })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });

            const approveButtons = screen.getAllByText('Approve');
            fireEvent.click(approveButtons[0]);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/update-user-approval',
                    expect.objectContaining({
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            Authorization: 'Bearer test-token'
                        },
                        body: JSON.stringify({ userId: 1, action: 'approve' })
                    })
                );
            });
        });

        test('rejects user successfully', async () => {
            mockFetch.mockImplementation((url, options) => {
                if (url.includes('/api/update-user-approval')) {
                    return Promise.resolve({
                        ok: true,
                        json: async () => ({ message: 'User rejected successfully' })
                    });
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: mockPendingUsers })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });

            const rejectButtons = screen.getAllByText('Reject');
            fireEvent.click(rejectButtons[0]);

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith(
                    'http://localhost:3000/api/update-user-approval',
                    expect.objectContaining({
                        method: 'POST',
                        body: JSON.stringify({ userId: 1, action: 'reject' })
                    })
                );
            });
        });

        test('displays success message after approval', async () => {
            mockFetch.mockImplementation((url, options) => {
                if (url.includes('/api/update-user-approval')) {
                    return Promise.resolve({
                        ok: true,
                        json: async () => ({ message: 'User approved' })
                    });
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: mockPendingUsers })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });

            const approveButtons = screen.getAllByText('Approve');
            fireEvent.click(approveButtons[0]);

            await waitFor(() => {
                expect(screen.getByText('Success: User approved')).toBeInTheDocument();
            });
        });

        test('refreshes data after user action', async () => {
            let callCount = 0;
            mockFetch.mockImplementation((url, options) => {
                if (url.includes('/api/update-user-approval')) {
                    return Promise.resolve({
                        ok: true,
                        json: async () => ({ message: 'User approved' })
                    });
                }
                if (url.includes('/api/pending-users')) {
                    callCount++;
                    return Promise.resolve({
                        ok: true,
                        json: async () => ({ users: mockPendingUsers })
                    });
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: mockAllUsers })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });

            const initialCallCount = callCount;

            const approveButtons = screen.getAllByText('Approve');
            fireEvent.click(approveButtons[0]);

            await waitFor(() => {
                // Should call pending users again after approval
                expect(callCount).toBeGreaterThan(initialCallCount);
            });
        });

        test('disables buttons while loading', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });

            const approveButtons = screen.getAllByText('Approve');
            const rejectButtons = screen.getAllByText('Reject');

            approveButtons.forEach(button => {
                expect(button).not.toBeDisabled();
            });

            rejectButtons.forEach(button => {
                expect(button).not.toBeDisabled();
            });
        });
    });

    describe('Error Handling', () => {
        test('displays error message when fetching pending users fails', async () => {
            mockFetch.mockImplementation((url) => {
                if (url.includes('/api/pending-users')) {
                    return Promise.resolve({
                        ok: false,
                        status: 500,
                        json: async () => ({})
                    });
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: [] })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText(/Error: Failed to fetch pending users/i)).toBeInTheDocument();
            });
        });

        test('displays error message when fetching all users fails', async () => {
            mockFetch.mockImplementation((url) => {
                if (url.includes('/api/all-users')) {
                    return Promise.resolve({
                        ok: false,
                        status: 500,
                        json: async () => ({})
                    });
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: [] })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText(/Error: Failed to fetch all users/i)).toBeInTheDocument();
            });
        });

        test('displays error message when user action fails', async () => {
            mockFetch.mockImplementation((url, options) => {
                if (url.includes('/api/update-user-approval')) {
                    return Promise.resolve({
                        ok: false,
                        status: 500
                    });
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: mockPendingUsers })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });

            const approveButtons = screen.getAllByText('Approve');
            fireEvent.click(approveButtons[0]);

            await waitFor(() => {
                expect(screen.getByText(/Error: Failed to approve user/i)).toBeInTheDocument();
            });
        });

        test('handles network error gracefully', async () => {
            mockFetch.mockImplementation((url) => {
                if (url.includes('/api/pending-users')) {
                    return Promise.reject(new Error('Network error'));
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: [] })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText(/Error: Network error/i)).toBeInTheDocument();
            });
        });
    });

    describe('Empty States', () => {
        test('shows empty state when no pending users', async () => {
            mockFetch.mockImplementation((url) => {
                if (url.includes('/api/pending-users')) {
                    return Promise.resolve({
                        ok: true,
                        json: async () => ({ users: [] })
                    });
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: mockAllUsers })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('No users pending approval')).toBeInTheDocument();
            });
        });

        test('shows empty state when no users at all', async () => {
            mockFetch.mockImplementation(() => {
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: [] })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
            });

            const allUsersTab = screen.getByText(/All Users/i);
            fireEvent.click(allUsersTab);

            await waitFor(() => {
                expect(screen.getByText('No users found')).toBeInTheDocument();
            });
        });
    });

    describe('Status Badges', () => {
        test('displays "Email Not Verified" badge for unverified users', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('Email Not Verified')).toBeInTheDocument();
            });
        });

        test('displays "Pending Approval" badge for verified but unapproved users', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('Pending Approval')).toBeInTheDocument();
            });
        });

        test('displays "Approved" badge for approved users in all users tab', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
            });

            const allUsersTab = screen.getByText(/All Users/i);
            fireEvent.click(allUsersTab);

            await waitFor(() => {
                expect(screen.getByText('Approved')).toBeInTheDocument();
            });
        });
    });

    describe('Date Formatting', () => {
        test('formats dates correctly', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                const dateElements = screen.getAllByText(/2024/);
                expect(dateElements.length).toBeGreaterThan(0);
            });
        });

        test('displays dash for null approved date', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
            });

            const allUsersTab = screen.getByText(/All Users/i);
            fireEvent.click(allUsersTab);

            await waitFor(() => {
                const cells = screen.getAllByText('-');
                expect(cells.length).toBeGreaterThan(0);
            });
        });
    });

    describe('Navigation', () => {
        test('navigates to landing page when back button is clicked', async () => {
            render(<UserApproval />);

            const backButton = screen.getByText(/Back to Landing Page/i);
            fireEvent.click(backButton);

            expect(mockNavigate).toHaveBeenCalledWith('/landing');
        });
    });

    describe('Table Rendering', () => {
        test('renders pending users table with all columns', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('Username')).toBeInTheDocument();
                expect(screen.getByText('Email')).toBeInTheDocument();
                expect(screen.getByText('Role')).toBeInTheDocument();
                expect(screen.getByText('Registration Date')).toBeInTheDocument();
                expect(screen.getByText('Status')).toBeInTheDocument();
                expect(screen.getByText('Actions')).toBeInTheDocument();
            });
        });

        test('renders all users table with additional columns', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
            });

            const allUsersTab = screen.getByText(/All Users/i);
            fireEvent.click(allUsersTab);

            await waitFor(() => {
                expect(screen.getByText('Approved By')).toBeInTheDocument();
                expect(screen.getByText('Approved Date')).toBeInTheDocument();
            });
        });

        test('displays correct number of rows in pending users table', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
                expect(screen.getByText('pendinguser2')).toBeInTheDocument();
            });
        });

        test('displays correct number of rows in all users table', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
            });

            const allUsersTab = screen.getByText(/All Users/i);
            fireEvent.click(allUsersTab);

            await waitFor(() => {
                expect(screen.getByText('approveduser')).toBeInTheDocument();
                expect(screen.getByText('rejecteduser')).toBeInTheDocument();
            });
        });
    });

    describe('Edge Cases', () => {
        test('handles user with null approved_by field', async () => {
            const usersWithNull = [
                {
                    id: 5,
                    username: 'user5',
                    email: 'user5@example.com',
                    role: 'user',
                    createdAt: '2024-01-10T09:00:00Z',
                    is_verified: true,
                    is_approved: false,
                    approved_by: null,
                    approved_at: null
                }
            ];

            mockFetch.mockImplementation((url) => {
                if (url.includes('/api/all-users')) {
                    return Promise.resolve({
                        ok: true,
                        json: async () => ({ users: usersWithNull })
                    });
                }
                return Promise.resolve({
                    ok: true,
                    json: async () => ({ users: [] })
                });
            });

            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
            });

            const allUsersTab = screen.getByText(/All Users/i);
            fireEvent.click(allUsersTab);

            await waitFor(() => {
                expect(screen.getByText('user5')).toBeInTheDocument();
            });
        });

        test('handles multiple rapid tab switches', async () => {
            render(<UserApproval />);

            await waitFor(() => {
                expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
            });

            const allUsersTab = screen.getByText(/All Users/i);
            const pendingTab = screen.getByText(/Pending Approvals/i);

            fireEvent.click(allUsersTab);
            fireEvent.click(pendingTab);
            fireEvent.click(allUsersTab);
            fireEvent.click(pendingTab);

            await waitFor(() => {
                expect(screen.getByText('pendinguser1')).toBeInTheDocument();
            });
        });

        test('handles empty token string', async () => {
            mockLocalStorage.getItem.mockReturnValue('');

            render(<UserApproval />);

            await waitFor(() => {
                expect(global.alert).toHaveBeenCalledWith('No token found, please log in.');
                expect(mockNavigate).toHaveBeenCalledWith('/');
            });
        });
    });
});