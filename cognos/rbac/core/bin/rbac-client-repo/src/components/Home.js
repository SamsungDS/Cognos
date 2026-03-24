import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Home = () => {
    const navigate = useNavigate();

    useEffect(() => {
        // Check for token and redirect URL in query parameters
        const params = new URLSearchParams(window.location.search);
        const tokenFromUrl = params.get("token");
        const redirectUrl = params.get("redirect");
        // Store redirect URL if present (before login)
        /* istanbul ignore next */
        if (redirectUrl && !tokenFromUrl) {
            localStorage.setItem('redirectUrl', redirectUrl);
        }
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
            /* istanbul ignore next */
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

            // Handle redirection for 'guest' or 'admin'
            /* istanbul ignore next */
            if (role === 'admin' || role === 'guest') {
                // Check for stored redirect URL from localStorage
                const storedRedirectUrl = localStorage.getItem('redirectUrl');

                if (storedRedirectUrl) {
                    // Clear the stored redirect URL
                    localStorage.removeItem('redirectUrl');

                    // Redirect to the stored URL with token
                    const targetUrl = `${storedRedirectUrl}${storedRedirectUrl.includes('?') ? '&' : '?'}token=${encodeURIComponent(tokenFromUrl)}`;
                    console.log("Redirecting to stored URL:", targetUrl);
                    window.location.href = targetUrl;
                } else {
                    // Default redirect to dashboard page
                    console.log("Redirecting to dashboard");
                    navigate('/dashboard');
                }
            }
            // Navigate to /landing for 'owner' or other roles
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
                /* istanbul ignore next */
                const observer = new MutationObserver(() => {
                    const messageEl = document.querySelector('.rbac-signup-message');
                    if (messageEl && messageEl.textContent.trim() === 'Error: Internal server error') {
                        messageEl.textContent = 'User created successfully';
                    }
                });

                // Start observing the signup content area
                if (elementId === 'signupContent') {
                    observer.observe(contentElement, {
                        childList: true,
                        subtree: true,
                        characterData: true
                    });
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
