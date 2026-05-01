import React from 'react';
import { Button, Container, Row, Col, Table } from 'react-bootstrap';
import './Developer.css'
import './configure.css';
import { color } from 'd3';

const Developer = () => {
  return (
      <div className='Content content_root about' id='main-container'>
        <h1 className='heading_name'>
            Experimental Page
        </h1>
        <h2 className='h2 heading_name' style={{color: '#fff'}}>
            Use this page to test unique features of Cognos.
            Add key-value pairs for each arg typically required in the "command_params" map per the feature
        </h2>
        <Container fluid className="content_root" id="configure-container-id">
          <Row>
            <Col>
              <div className="device_card" style={{ height: "336px" }}>
                <div
                  className="table-div"
                  data-testid="table-div-id"
                  style={{ maxHeight: "300px", overflowY: "auto" }}
                >
                  <Table responsive className="custom-table" variant="dark" style={{ fontFamily: "Samsung sharp sons" }}>
                    <thead>
                      <tr>
                        <th className="cofig-row">Feature</th>
                        <th className="cofig-row">Description</th>
                        <th className="cofig-row">Status</th>
                        <th className="cofig-row">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td className="cofig-row">move</td>
                        <td className="cofig-row">Migrates data based on desired SLA</td>
                        <td className="cofig-row">Idle</td>
                        <td className="cofig-row">+</td>
                      </tr>
                      <tr>
                        <td className="cofig-row">move_all</td>
                        <td className="cofig-row">Migrates all data from one numa node to another</td>
                        <td className="cofig-row">idle</td>
                        <td className="cofig-row">+</td>
                      </tr>
                    </tbody>
                  </Table>
                </div>
              </div>
            </Col>
          </Row>

        </Container>
      </div>
  )
}
export default Developer;