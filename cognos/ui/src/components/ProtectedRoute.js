import React, { useEffect, useState, createContext, useMemo } from 'react';
import { Navigate } from 'react-router-dom';
import * as constants from '../constant';
// Create a context for authentication data
export const AuthContext = createContext(null);

const ProtectedRoute = ({ children, allowedRoles = [] }) => {
    const rbacEndpoint = constants.Configs.rbac_endpoint;
    const [isAuthenticated, setIsAuthenticated] = useState(null);
    const [userRole, setUserRole] = useState(null);
    function getUserRole(token) {
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
    }

    useEffect(() => {
        const verifyToken = async () => {            
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token');


            if (token) {
                window.history.replaceState({}, document.title, window.location.pathname);
            }

            if (!token) {
                // Redirect to login application
                handleRedirectToLogin();               
            } else {
                setIsAuthenticated(true);
                const decoded = getUserRole(token);
                console.log("User Role:", decoded.role);
                setUserRole(decoded.role);
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
    }, []);

    // Memoize the context value to prevent unnecessary re-renders
    const authContextValue = useMemo(() => ({
        userRole,
        isAuthenticated
    }), [userRole, isAuthenticated]);
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