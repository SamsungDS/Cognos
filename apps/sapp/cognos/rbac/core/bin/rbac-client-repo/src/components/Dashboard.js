import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Dashboard = () => {
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
          throw new Error('Network response was not ok');
        }
        const data = await response.text();
        const contentElement = document.getElementById(elementId);
        contentElement.innerHTML = data;

        // Execute any inline scripts from the fetched content
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

    loadComponent('/dashboard', 'dashboardContent');
  }, [navigate]);

  return (
    <div>
      <button onClick={() => navigate('/landing')}>Back to Landing Page</button>
      <div id="dashboardContent"></div>
    </div>
  );
};

export default Dashboard;
