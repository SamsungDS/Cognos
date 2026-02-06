import React, { useEffect } from "react";
import { Route, BrowserRouter, Routes, Navigate } from "react-router-dom";
import "./App.css";
import "bootstrap/dist/css/bootstrap.min.css";
import Header from "./components/Header";
import SideBar from "./components/SideBar";
import Metrics from "./pages/Metrics";
import Dashboard from "./pages/Dashboard";
// import Configure from "./pages/Configure";
import About from "./pages/About";
import Jobs from "./pages/Jobs";
import Events from './pages/Events';
import DeviceStats from './pages/DeviceStats';
import DownloadArtifacts from "./pages/DownloadArtifacts";
import { EventsProvider } from './contexts/EventsContext';
import ProtectedRoute from "./components/ProtectedRoute";
import * as constants from './constant';
// Configuration flag - set true enable downlaod artifacts on AWS
const DOWNLOAD_ONLY_MODE = constants.Configs.download_only_mode;

function App() {
  // Check if token exists in URL parameters (for redirect from login page)
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get("token");

    if (token) {
      // Remove token from URL for security while preserving the path
      const cleanUrl = window.location.origin + window.location.pathname;
      window.history.replaceState({}, document.title, cleanUrl);
    }
  }, []);

  return (
    <EventsProvider>
      <BrowserRouter>
        <Routes>
          {DOWNLOAD_ONLY_MODE ? (
            // Download-only mode: Only show Download Artifacts page (no sidebar)
            <>
              <Route
                path="/"
                element={
                  <ProtectedRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <DownloadArtifacts />
                    </div>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/download-artifacts"
                element={
                  <ProtectedRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <DownloadArtifacts />
                    </div>
                  </ProtectedRoute>
                }
              />
              {/* Redirect all other routes to home */}
              <Route
                path="*"
                element={<Navigate to="/" replace />}
              />
            </>
          ) : (
            // Full application mode: Show all routes with sidebar
            <>
              {/* Redirect root to /dashboard */}
              <Route
                path="/"
                element={<Navigate to="/dashboard" replace />}
              />

              <Route
                path="/dashboard"
                element={
                  <ProtectedRoute>
                    <div className="grid-container">
                      <Header />
                      <SideBar>
                        <Dashboard />
                      </SideBar>
                    </div>
                  </ProtectedRoute>
                }
              />

              {/* <Route
                path="/configure"
                element={
                  <ProtectedRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <SideBar>
                        <Configure />
                      </SideBar>
                    </div>
                  </ProtectedRoute>
                }
              /> */}

              <Route
                path="/metrics"
                element={
                  <ProtectedRoute>
                    <div className="grid-container">
                      <Header />
                      <SideBar>
                        <Metrics />
                      </SideBar>
                    </div>
                  </ProtectedRoute>
                }
              />

              <Route
                path="/device-stats"
                element={
                  <ProtectedRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <SideBar>
                        <DeviceStats />
                      </SideBar>
                    </div>
                  </ProtectedRoute>
                }
              />

              <Route
                path="/application_view"
                element={
                  <ProtectedRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <SideBar>
                        <Jobs />
                      </SideBar>
                    </div>
                  </ProtectedRoute>
                }
              />

              <Route
                path="/events"
                element={
                  <ProtectedRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <SideBar>
                        <Events />
                      </SideBar>
                    </div>
                  </ProtectedRoute>
                }
              />

              <Route
                path="/download_artifacts"
                element={
                  <ProtectedRoute allowedRoles={["admin"]}>
                    <div className="grid-container">
                      <Header />
                      <SideBar>
                        <DownloadArtifacts />
                      </SideBar>
                    </div>
                  </ProtectedRoute>
                }
              />

              <Route
                path="/about"
                element={
                  <ProtectedRoute>
                    <div className="grid-container">
                      <Header />
                      <SideBar>
                        <About />
                      </SideBar>
                    </div>
                  </ProtectedRoute>
                }
              />
            </>
          )}
        </Routes>
      </BrowserRouter>
    </EventsProvider>
  );
}

export default App;