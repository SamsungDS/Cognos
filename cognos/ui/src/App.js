import React, { useState, useEffect } from "react";
import { Route, BrowserRouter, Routes, Navigate } from "react-router-dom";
import "./App.css";
import "bootstrap/dist/css/bootstrap.min.css";
import Header from "./components/Header";
import SideBar from "./components/SideBar";
import Metrics from "./pages/Metrics";
import Dashboard from "./pages/Dashboard";
import About from "./pages/About";
import Jobs from "./pages/Jobs";
import Events from './pages/Events';
import DeviceStats from './pages/DeviceStats';
import DownloadArtifacts from "./pages/DownloadArtifacts";
import { EventsProvider } from './contexts/EventsContext';
import ProtectedRoute from "./components/ProtectedRoute";
import * as constants from './constant';

const apiEndpoint = constants.Configs.api_endpoint;
// Set to false to bypass authentication entirely
const RBAC_ENABLED = constants.Configs.rbac_enabled;

// Wrapper: renders ProtectedRoute only when login is enabled
const AuthRoute = ({ children, allowedRoles }) => {
  if (!RBAC_ENABLED) return children;
  return <ProtectedRoute allowedRoles={allowedRoles}>{children}</ProtectedRoute>;
};

function App() {
  const [downloadMode, setDownloadMode] = useState(false);
  // istanbul ignore next
  useEffect(() => {
    const checkArtifacts = async () => {
      try {
        const res = await fetch(`${apiEndpoint}/list_artifact`, {
          mode: 'cors',
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'Access-Control-Allow-Origin': '*'
          },
        });
        if (res.ok) setDownloadMode(true);
      } catch {
        setDownloadMode(false);
      }
    };
    checkArtifacts();
  }, []);

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get("token");
    if (token) {
      const cleanUrl = window.location.origin + window.location.pathname;
      window.history.replaceState({}, document.title, cleanUrl);
    }
  }, []);

  
  // Download mode: render without EventsProvider — stops all other API calls
  // istanbul ignore next
  if (downloadMode) {
    return (
      <BrowserRouter>
        <Routes>
          <Route
            path="/"
            element={
              <AuthRoute allowedRoles={["admin"]}>
                <div className="grid-container">
                  <Header />
                  <DownloadArtifacts />
                </div>
              </AuthRoute>
            }
          />
          <Route
            path="/download-artifacts"
            element={
              <AuthRoute allowedRoles={["admin"]}>
                <div className="grid-container">
                  <Header />
                  <DownloadArtifacts />
                </div>
              </AuthRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    );
  }
  return (
    <EventsProvider>
      <BrowserRouter>
        <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />

              <Route
                path="/dashboard"
                element={
                  <AuthRoute>
                    <div className="grid-container">
                      <Header />
                      <SideBar><Dashboard /></SideBar>
                    </div>
                  </AuthRoute>
                }
              />

              <Route
                path="/metrics"
                element={
                  <AuthRoute>
                    <div className="grid-container">
                      <Header />
                      <SideBar><Metrics /></SideBar>
                    </div>
                  </AuthRoute>
                }
              />

              <Route
                path="/device-stats"
                element={
                  <AuthRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <SideBar><DeviceStats /></SideBar>
                    </div>
                  </AuthRoute>
                }
              />

              <Route
                path="/application_view"
                element={
                  <AuthRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <SideBar><Jobs /></SideBar>
                    </div>
                  </AuthRoute>
                }
              />

              <Route
                path="/events"
                element={
                  <AuthRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <SideBar><Events /></SideBar>
                    </div>
                  </AuthRoute>
                }
              />

              <Route
                path="/about"
                element={
                  <AuthRoute>
                    <div className="grid-container">
                      <Header />
                      <SideBar><About /></SideBar>
                    </div>
                  </AuthRoute>
                }
              />
        </Routes>
      </BrowserRouter>
    </EventsProvider>
  );
}

export default App;