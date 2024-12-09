import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { SelectedOptionProvider } from './contexts/SelectedOptionContext';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <WebSocketProvider>
        <SelectedOptionProvider>
            <App />
        </SelectedOptionProvider>
    </WebSocketProvider>    
);


