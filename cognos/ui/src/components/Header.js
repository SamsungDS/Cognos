import React from "react";
import SamsungLogo from "../assets/images/logos/samsung_logo_lettermark_white.PNG";
import { Row, Col } from "react-bootstrap";

const Header = () => {

  return (
    <div className="Header" id="header-container-id">
      <Row>
        <Col>
          {" "}
          <header className="heading">
            <div style={{ display: "flex" }}>
              <img
                src={SamsungLogo}
                alt="logo"
                style={{ objectFit: "contain", width: 180, margin: 20, marginBottom:6 }}
              />{" "}
              <span className="fs-22" style={{ marginTop: 14, fontSize: 24 }}>
                {" "}
                | &nbsp; &nbsp; Cognos Management Console
              </span>
            </div>
          </header>
        </Col>
      </Row>
    </div>
  );
};

export default Header;