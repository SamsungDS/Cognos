import React, { useEffect, useState, createContext, useMemo } from 'react';
import { Navigate } from 'react-router-dom';
import * as constants from '../constant';
// Create a context for authentication data
export const AuthContext = createContext(null);
export const getUserRole = (token) => {
    try {
        localStorage.setItem('token', token);
        const base64Url = token.split('.')[1]; // Get payload part
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');

        // Add padding if needed
        const padded = base64.padEnd(base64.length + (4 - base64.length % 4) % 4, '=');

        const jsonPayload = decodeURIComponent(
            atob(padded)
                .split('')
                .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
                .join('')
        );

        return JSON.parse(jsonPayload);
    } catch (error) {
        console.error('Error decoding token:', error);
        return null;
    }
};
// New function to validate token expiration
export const isTokenValid= (token) => {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const padded = base64.padEnd(base64.length + (4 - base64.length % 4) % 4, '=');
        const jsonPayload = decodeURIComponent(
            atob(padded)
                .split('')
                .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
                .join('')
        );
        const decoded = JSON.parse(jsonPayload);

        // Check if token is expired
        const currentTime = Date.now() / 1000;
        return decoded.exp > currentTime;
    } catch (error) {
        console.error('Error validating token:', error);
        return false;
    }
};
// ProtectedRoute is allow permission to users
const ProtectedRoute = ({ children, allowedRoles = [] }) => {
    const rbacEndpoint = constants.Configs.rbac_endpoint;
    const [isAuthenticated, setIsAuthenticated] = useState(null);
    const [userRole, setUserRole] = useState(null);    
    // New function to clear auth data
    // istanbul ignore next
    function clearAuthData() {
        localStorage.removeItem('token');
        setIsAuthenticated(false);
        setUserRole(null);
    }

    useEffect(() => {
        const verifyToken = async () => {
            const urlParams = new URLSearchParams(window.location.search);
            const urlToken = urlParams.get('token');

            // Check localStorage for existing token
            const storedToken = localStorage.getItem('token');

            let tokenToUse = null;

            // Prioritize URL token over stored token (for new logins)
            // istanbul ignore next
            if (urlToken) {
                window.history.replaceState({}, document.title, window.location.pathname);
                tokenToUse = urlToken;
            } else if (storedToken) {
                tokenToUse = storedToken;
            }

            if (!tokenToUse) {
                // No token found, redirect to login application
                handleRedirectToLogin();
            } else {
                // Validate token before using it
                if (!isTokenValid(tokenToUse)) {
                    // Token is invalid or expired, clear storage and redirect
                    clearAuthData();
                    handleRedirectToLogin();
                    return;
                }

                // Token is valid
                // istanbul ignore next
                setIsAuthenticated(true);
                const decoded = getUserRole(tokenToUse);

                // istanbul ignore next
                if (decoded) {                   
                    setUserRole(decoded.role);
                } else {
                    // Failed to decode valid token, clear and redirect
                    clearAuthData();
                    handleRedirectToLogin();
                }
            }
        };

        const handleRedirectToLogin = () => {
            const currentPath = window.location.pathname + window.location.search;
            const currentUrl = window.location.origin + currentPath;
            // Pass redirect URL as query parameter
            const redirectParam = encodeURIComponent(currentUrl);
            window.location.href = `${rbacEndpoint}?redirect=${redirectParam}`;
        };

        verifyToken();
    }, [rbacEndpoint]);

    // Memoize the context value to prevent unnecessary re-renders
    // istanbul ignore next
    const authContextValue = useMemo(() => ({
        userRole,
        isAuthenticated,
        // Add logout function to context       
        logout: () => {
            clearAuthData();
            const currentPath = window.location.pathname + window.location.search;
            const currentUrl = window.location.origin + currentPath;
            const redirectParam = encodeURIComponent(currentUrl);
            window.location.href = `${rbacEndpoint}?redirect=${redirectParam}`;
        }
    }), [userRole, isAuthenticated, rbacEndpoint]);

    if (isAuthenticated === null) {
        // Still checking authentication
        return <div>Loading...</div>;
    }

    // Check if user role is allowed for this route
    // istanbul ignore next
    if (allowedRoles.length > 0 && !allowedRoles.includes(userRole)) {
        return <Navigate to="/" replace />;
    }

    // Provide auth data to all nested components using Context
    // istanbul ignore next
    return isAuthenticated ? (
        <AuthContext.Provider value={authContextValue}>
            {children}
        </AuthContext.Provider>
    ) : null;
};

export default ProtectedRoute;