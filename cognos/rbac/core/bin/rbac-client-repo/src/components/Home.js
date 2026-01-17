import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Home = () => {
    const navigate = useNavigate();

    useEffect(() => {
        // Check for token in URL query parameters
        const params = new URLSearchParams(window.location.search);
        const tokenFromUrl = params.get("token");
        // ====== TOKEN HANDLING & REDIRECTION LOGIC ======
        if (tokenFromUrl) {
            // Store token
            localStorage.setItem('token', tokenFromUrl);
            // Decode JWT to extract role
            const getRoleFromToken = (token) => {
                try {
                    const parts = token.split('.');

                    if (parts.length !== 3) {
                        console.error('Invalid token structure');
                        return null;
                    }

                    const payload = JSON.parse(atob(parts[1]));
                    return payload.role;
                } catch (err) {
                    console.error('Error decoding token:', err);
                    return null;
                }
            };

            const role = getRoleFromToken(tokenFromUrl);

            if (role === null || role === undefined) {
                navigate('/landing');
                return;
            }

            // Attach token to fetch
            if (window.fetch) {
                const originalFetch = window.fetch;
                window.fetch = function (url, options = {}) {
                    options.headers = {
                        ...options.headers,
                        Authorization: `Bearer ${tokenFromUrl}`,
                    };
                    return originalFetch(url, options);
                };
            }

            // Remove token from URL
            window.history.replaceState({}, document.title, window.location.pathname);

            // CHANGED: Only redirect to port 5000 for 'user' or 'admin'
            if (role === 'user' || role === 'admin') {
                // Build redirect URL to port 5000
                const currentProtocol = window.location.protocol;
                const currentHostname = window.location.hostname;
                const redirectUrl = `${currentProtocol}//${currentHostname}:5000/?token=${encodeURIComponent(tokenFromUrl)}`;
                window.location.href = redirectUrl;
            }
            // CHANGED: Navigate to /landing for 'owner' or other roles
            else {
                navigate('/landing');
            }

            return; // Exit early
        }
        // ====== END TOKEN HANDLING ======

        // ====== EXISTING LOGIC ======
        const loadComponent = async (path, elementId) => {
            try {
                const response = await fetch(
                    `${process.env.REACT_APP_BACKEND_URL}/api${path}?style=true`
                );

                if (!response.ok) {
                    throw new Error(`HTTP error: ${response.status}`);
                }

                const data = await response.text();
                const contentElement = document.getElementById(elementId);
                if (contentElement) {
                    contentElement.innerHTML = data;

                    const scripts = contentElement.getElementsByTagName('script');
                    for (let script of scripts) {
                        const newScript = document.createElement('script');
                        newScript.textContent = script.textContent;
                        document.body.appendChild(newScript);
                    }
                }
            } catch (error) {
                console.error('Error loading page:', error);
            }
        };

        loadComponent('/login', 'loginContent');
        loadComponent('/signup', 'signupContent');

        const handleLoginSuccess = (event) => {
            const { token } = event.detail;

            if (token) {
                const currentPath = window.location.pathname;
                const newUrl = `${currentPath}?token=${encodeURIComponent(token)}`;
                // Reload page with token in URL
                window.location.href = newUrl;
            } else {
                navigate('/landing');
            }
        };

        window.addEventListener('rbacLogin', handleLoginSuccess);

        return () => {
            window.removeEventListener('rbacLogin', handleLoginSuccess);
        };
    }, [navigate]);

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

export default Home;
