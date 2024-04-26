import React from 'react';
import { Route, BrowserRouter, Routes } from "react-router-dom";
import './App.css';
import 'bootstrap/dist/css/bootstrap.min.css';
import Header from './components/Header';
import SideBar from './components/SideBar';
import Metrics from './pages/Metrics';
import Dashboard from './pages/Dashboard';

function App() {

  return (
      <div className='grid-container'>
        <Header/>
        <BrowserRouter>
          <SideBar>
            <Routes><Route path='/' element={<Dashboard/>}/></Routes>
            <Routes><Route path='/metrics' element={<Metrics/>}/></Routes>
          </SideBar>
        </BrowserRouter>
      </div>
  );
}

export default App;
