import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import ProtectedRoute from '../components/ProtectedRoute';
import { MemoryRouter } from 'react-router-dom';
import * as constants from '../constant';




// Mock atob (base64 decoder) for JWT payload decoding
global.atob = (str) => Buffer.from(str, 'base64').toString('binary');

const createMockToken = (role = 'admin') => {
    const payload = {
        role: role,
    };
    const base64Payload = Buffer.from(JSON.stringify(payload)).toString('base64url');
    return `header.${base64Payload}.signature`;
};

// Helper to set window.location and search params
const setTokenInUrl = (token) => {
    const url = `http://localhost/?token=${token}`;
    delete window.location;
    window.location = new URL(url);
    jest.spyOn(window.history, 'replaceState').mockImplementation(() => { });
};

describe('ProtectedRoute', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    test('redirects to / if user role is not allowed', async () => {
        const token = createMockToken('guest');
        setTokenInUrl(token);

        render(
            <MemoryRouter initialEntries={['/protected']}>
                <ProtectedRoute allowedRoles={['admin']}>
                    <div>Protected Content</div>
                </ProtectedRoute>
            </MemoryRouter>
        );

        await waitFor(() => {
            // Will not find protected content
            expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
        });
    });

});
