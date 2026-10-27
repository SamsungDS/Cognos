import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import { SelectedOptionProvider } from './contexts/SelectedOptionContext';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <SelectedOptionProvider>
        <App />
    </SelectedOptionProvider>
);


