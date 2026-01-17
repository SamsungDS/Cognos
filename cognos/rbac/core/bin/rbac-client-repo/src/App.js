import React from 'react';
import { Route, Routes } from 'react-router-dom';
import Home from './components/Home';
import Profile from './components/Profile';
import Dashboard from './components/Dashboard';
import LandingPage from './components/LandingPage';
import Settings from './components/Settings';
import UserApproval from './components/UserApproval';
import './App.css';

const App = () => (
  <div className="App">
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/landing" element={<LandingPage />} />
      <Route path="/profile" element={<Profile />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/user-approval" element={<UserApproval />} />
    </Routes>
  </div>
);

export default App;
