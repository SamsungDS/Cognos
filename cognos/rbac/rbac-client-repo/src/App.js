import React from 'react';
import { Route, Routes } from 'react-router-dom';
import Login from './components/Login';
import './App.css';

const App = () => (
  <div className="App">
    <Routes>
      <Route path="/" element={<Login />} />
    </Routes>
  </div>
);

export default App;
