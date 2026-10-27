import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Profile = () => {
  const navigate = useNavigate();

  useEffect(() => {
    const loadComponent = async (path, elementId) => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          alert('No token found, please log in.');
          navigate('/');
          return;
        }

        const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api${path}?style=true`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        
        if (!response.ok) {
          throw new Error(`HTTP error: ${response.status}`);
        }
        
        const data = await response.text();
        const contentElement = document.getElementById(elementId);
        contentElement.innerHTML = data;

        const scripts = contentElement.getElementsByTagName('script');
        for (let script of scripts) {
          const newScript = document.createElement('script');
          newScript.textContent = script.textContent;
          document.body.appendChild(newScript);
        }
      } catch (error) {
        alert(`Error loading ${path} page. Redirecting to home.`);
        navigate('/');
      }
    };

    loadComponent('/profile', 'profileContent');
  }, [navigate]);

  return (
    <div>
      <button onClick={() => navigate('/landing')}>Back to Landing Page</button>
      <div id="profileContent"></div>
    </div>
  );
};

export default Profile;
