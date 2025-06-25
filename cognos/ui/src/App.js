import React from 'react';
import { Route, BrowserRouter, Routes } from "react-router-dom";
import './App.css';
import 'bootstrap/dist/css/bootstrap.min.css';
import Header from './components/Header';
import SideBar from './components/SideBar';
import Metrics from './pages/Metrics';
import Dashboard from './pages/Dashboard';
import Configure from './pages/Configure';
import About from './pages/About';
import Jobs from './pages/Jobs';

function App() {

  return (
      <div className='grid-container'>
        <Header/>
        <BrowserRouter>
          <SideBar>
            <Routes><Route path='/' element={<Dashboard/>} forceRefresh={true}/></Routes>
            <Routes><Route path='/Configure' element={<Configure/>}/></Routes>
            <Routes><Route path='/metrics' element={<Metrics/>}/></Routes>
            <Routes><Route path='/About' element={<About/>}/></Routes>
            <Routes><Route path='/jobs' element={<Jobs/>}/></Routes>
          </SideBar>
        </BrowserRouter>
      </div>
  );
}

export default App;
