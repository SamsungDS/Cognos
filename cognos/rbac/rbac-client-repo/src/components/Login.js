import React, { useEffect, useCallback } from "react";
import config from '../config/config.json';

const Login = () => {
    const svkAppEndpoint = config.mgmt_endpoint;
    const rbacBackendEndpoint = config.rbac_backend_endpoint;

    // Extract script execution logic
    // istanbul ignore next
    const executeScripts = useCallback((contentElement) => {
        const scripts = contentElement.getElementsByTagName("script");
        for (let script of scripts) {
            const newScript = document.createElement("script");
            newScript.textContent = script.textContent;
            document.body.appendChild(newScript);
        }
    }, []);

    // Extract signup customization logic
    // istanbul ignore next
    const customizeSignupForm = useCallback(() => {
        const interval = setInterval(() => {
            const roleSelect = document.getElementById('rbac-role');
            const title = document.querySelector('#rbac-signup-container h1');
            const roleGroup = roleSelect?.closest('.rbac-signup-form-group');

            if (roleSelect && title && roleGroup) {
                roleSelect.value = 'guest';
                roleGroup.style.display = 'none';
                title.textContent = 'Register As Guest User';
                clearInterval(interval);
            }
        }, 100);

        // Safety stop after 5 seconds
        setTimeout(() => clearInterval(interval), 5000);
    }, []);

    // Extract component loading logic
    const loadComponent = useCallback(async (path, elementId) => {
        try {
            const response = await fetch(
                `${rbacBackendEndpoint}/api${path}?style=true`
            );

            if (!response.ok) {
                // istanbul ignore next
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.text();
            const contentElement = document.getElementById(elementId);
            contentElement.innerHTML = data;

            executeScripts(contentElement);

            // Apply signup customization only for signup component
            if (path === '/signup') {
                customizeSignupForm();
            }
        } catch (error) {
            // istanbul ignore next
            console.error(`Error loading ${path}:`, error);
        }
    }, [rbacBackendEndpoint, executeScripts, customizeSignupForm]);

    // Extract redirect URL building logic
    // istanbul ignore next
    const buildRedirectUrl = useCallback((token) => {
        const urlParams = new URLSearchParams(window.location.search);
        const redirectUrl = urlParams.get('redirect');

        if (redirectUrl) {
            const targetUrl = `${decodeURIComponent(redirectUrl)}?token=${token}`;
            console.log("Redirecting to stored URL:", targetUrl);
            return targetUrl;
        } else {
            const targetUrl = `${svkAppEndpoint}?token=${token}`;
            console.log("Redirecting to dashboard:", targetUrl);
            return targetUrl;
        }
    }, [svkAppEndpoint]);

    // Extract login success handling logic
    // istanbul ignore next
    const handleLoginSuccess = useCallback((event) => {
        console.log("Login successful, navigating to landing page", event.detail.username);

        setTimeout(() => {
            const token = localStorage.getItem("token");
            if (token) {
                const targetUrl = buildRedirectUrl(token);
                window.location.href = targetUrl;
                localStorage.removeItem("token");
            }
        }, 100);
    }, [buildRedirectUrl]);

    // Simplified useEffect with reduced cognitive complexity
    useEffect(() => {
        // Load components
        loadComponent("/login", "loginContent");
        loadComponent("/signup", "signupContent");

        // Set up event listener
        window.addEventListener("rbacLogin", handleLoginSuccess);

        // Cleanup function
        return () => {
            window.removeEventListener("rbacLogin", handleLoginSuccess);
        };
    }, [loadComponent, handleLoginSuccess]);

    return (
        <div className="Home-page-style">
            <div style={{ height: '20px' }}></div>
            <div className="rbac-samsung-logo">
                <span className='rbac-samsung-logo'>SAMSUNG</span> Cognos Management Console
            </div>
            <div style={{ height: '40px' }}></div>

            <div style={{
                display: 'flex',
                flexDirection: 'row',
                gap: '40px',
                alignItems: 'flex-start',
                justifyContent: 'center',
                width: '100%',
                maxWidth: '1200px'
            }}>
                <div
                    id="loginContent"
                    style={{
                        flex: '1',
                        minWidth: '300px',
                        maxWidth: '500px'
                    }}
                />

                <div
                    id="signupContent"
                    style={{
                        flex: '1',
                        minWidth: '300px',
                        maxWidth: '500px'
                    }}
                />
            </div>
        </div>
    );
};

export default Login;