import React, { useState } from 'react';
import { Button, Container, Row, Col, Table } from 'react-bootstrap';
import './Developer.css'
import './configure.css';
import { color } from 'd3';
import * as constants from '../../src/constant';
import { DynamicFormModal } from '../components/forms/dynamicFormModal';

const Developer = () => {

  const [activeConfig, setActiveConfig] = useState(null);
  const [actionStatus, setActionStatus] = useState({
    move: "",
    move_all: "",
    get_move_stats: "",
    custom: ""
  });

  return (
      <div className='Content content_root about' id='main-container'>
        <h1 className='heading_name' style={{marginBottom: '50px'}}>
            Cognos API Sandbox
        </h1>
        <h2 className='h2 heading_name' style={{color: '#cec2c2', fontSize: '12px'}}>
            Use this page to test unique features of Cognos.
            Pass in the command args typically required per the feature
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
                        <td className="cofig-row">{actionStatus.move}</td>
                        <td className="cofig-row">
                          <Button
                            variant="outline-light"
                            size="sm"
                            onClick={() => {
                              setActiveConfig(constants.CognosMoveAPIArgs)
      
                            }}
                          >
                            <img
                              src={constants.AddIcon}
                              alt="add-Icon"
                              width="30"
                              height="auto"
                              style={{ objectFit: "cover" }}
                            />
                          </Button>
                        </td>
                      </tr>
                      <tr>
                        <td className="cofig-row">move_all</td>
                        <td className="cofig-row">Migrates all data from one numa node to another</td>
                        <td className="cofig-row">{actionStatus.move_all}</td>
                        <td className="cofig-row">
                          <Button
                            variant="outline-light"
                            size="sm"
                            onClick={() => setActiveConfig(constants.CognosMoveAllAPIArgs)}
                          >
                            <img
                              src={constants.AddIcon}
                              alt="add-Icon"
                              width="30"
                              height="auto"
                              style={{ objectFit: "cover" }}
                            />
                          </Button>
                        </td>
                      </tr>
                      <tr>
                        <td className="cofig-row">get_move_stats</td>
                        <td className="cofig-row">Get status of moved data</td>
                        <td className="cofig-row">{actionStatus.get_move_stats}</td>
                        <td className="cofig-row">
                          <Button
                            variant="outline-light"
                            size="sm"
                            onClick={() => setActiveConfig(constants.CognosMoveStatsAPIArgs)}
                          >
                            <img
                              src={constants.AddIcon}
                              alt="add-Icon"
                              width="30"
                              height="auto"
                              style={{ objectFit: "cover" }}
                            />
                          </Button>
                        </td>
                      </tr>
                    </tbody>
                  </Table>
                  <DynamicFormModal
                    config={activeConfig ?? constants.CognosMoveAPIArgs}
                    isOpen={!!activeConfig}
                    onClose={() => setActiveConfig(null)}
                    onSuccess={(data) => {
                      setActionStatus((prev) => ({
                        ...prev,
                        [activeConfig.title]: data.status
                      }))
                    }}
                  />
                </div>
              </div>
            </Col>
          </Row>

        </Container>
      </div>
  )
}
export default Developer;