import React, { useEffect } from "react";
import { Route, BrowserRouter, Routes } from "react-router-dom";
import "./App.css";
import "bootstrap/dist/css/bootstrap.min.css";
import Header from "./components/Header";
import SideBar from "./components/SideBar";
import Metrics from "./pages/Metrics";
import Dashboard from "./pages/Dashboard";
import Configure from "./pages/Configure";
import About from "./pages/About";
import Jobs from "./pages/Jobs";
import ProtectedRoute from "./components/ProtectedRoute";

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
    <BrowserRouter>
      <Routes>
        {/* Protected routes */}
        <Route
          path="/"
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

        <Route
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
        />

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
          path="/jobs"
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
      </Routes>
    </BrowserRouter>
  );
}

export default App;