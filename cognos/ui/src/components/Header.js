import React, { useContext } from "react";
import SamsungLogo from "../assets/images/logos/samsung_logo_lettermark_white.PNG";
import { Row, Col } from "react-bootstrap";
import * as constants from '../constant';
import { AuthContext } from './ProtectedRoute';

const RBAC_ENABLED = constants.Configs.rbac_enabled;

const Header = () => {
  const auth = useContext(AuthContext);
  const logout = RBAC_ENABLED ? auth?.logout : null;

  return (
    <div className="Header" id="header-container-id">
      <Row>
        <Col>
          <header className="heading">
            <div style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              width: "100%"
            }}>
              <div style={{ display: "flex", alignItems: "center" }}>
                <img
                  src={SamsungLogo}
                  alt="logo"
                  style={{
                    objectFit: "contain",
                    width: 180,
                    margin: 20,
                    marginBottom: 6
                  }}
                />
                <span
                  className="fs-22"
                  style={{
                    marginTop: 14,
                    fontSize: 24
                  }}
                >
                  | &nbsp; &nbsp; Cognos Management Console
                </span>
              </div>

              {/* Only render logout button when login is enabled */}
              {RBAC_ENABLED && (
                <button
                  onClick={logout}
                  style={{
                    backgroundColor: "#dc3545",
                    color: "white",
                    border: "none",
                    padding: "8px 16px",
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontSize: "14px",
                    fontWeight: "500",
                    marginRight: "20px",
                    transition: "background-color 0.3s ease",
                    boxShadow: "0 2px 4px rgba(0,0,0,0.1)"
                  }}
                  onMouseOver={(e) => {
                    e.target.style.backgroundColor = "#c82333";
                  }}
                  onMouseOut={(e) => {
                    e.target.style.backgroundColor = "#dc3545";
                  }}
                >
                  Logout
                </button>
              )}
            </div>
          </header>
        </Col>
      </Row>
    </div>
  );
};

export default Header;