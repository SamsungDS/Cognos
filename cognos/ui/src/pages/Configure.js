import React, { useState, useEffect} from 'react';
import { Button, Container, Row, Col, Table } from 'react-bootstrap'
import useAttachHook from '../customhooks/useAttachHook';
import AttachMemory from '../components/popups/AttachMemory';

import './configure.css'
import './metrics.css'

import { Configs, AddIcon,
  lmdTableHeader } from '../../src/constant';

const Configure = () => {

  const apiEndpoint = Configs.data_endpoint;
  const [showAttach, setShowAttach] = useState(false);
  const [selectedValue, setSelectedValue] = useState('');
  // used for top table
  const [lmdData, setLmdData] = useState([
    {
      lmd: 'D-1',
      mem_type: 'CMMD',
      mem_mode: 'Direct',
      capacity: 128,
      capacity_units: 'GB',
      used_capacity: 0,
      used_capacity_units: 'GB',
    }
  ]);
  // used for bottom table
  const [memboxData, setMemboxData] = useState([]);
  const [availableLMDs, setAvailableLMDs] = useState([]);

  // Attach and Detach use hook
  const { handleAttach } = useAttachHook(setMemboxData, setLmdData, () => setShowAttach(false), selectedValue, apiEndpoint);


  useEffect(() => {
    fetch(`${apiEndpoint}//lmds`)
      .then(response => response.json())
      .then(data => setMemboxData(data));
  }, 
  // eslint-disable-next-line react-hooks/exhaustive-deps 
  []);

  const getAvailableLMDS = async() => {
    const response = await fetch(`${apiEndpoint}//available_lmds`, {
      mode: 'cors',
      method: 'GET',
      headers: {'Content-Type': 'application/json'},
    });

    if (response.ok) {
      const data = await response.json();
      setAvailableLMDs(data);
    }
  };

  const handleAttachMemoryToggle = () => {
    getAvailableLMDS();
    setShowAttach(!showAttach);
  };
  


  const lmdTable =  Array.isArray ? lmdData.map(
    (item) => {
        return (
          <tr key={item.lmd}>
            <td className='cofig-row'>
            </td>
            <td className='cofig-row'>{item.lmd}</td>
            <td className='cofig-row'>{item.mem_type}</td>
            <td className='cofig-row'>{item.mem_mode}</td>
            <td className='cofig-row'>{item.capacity} {item.capacity_units}</td>
            <td className='cofig-row'>{item.used_capacity} {item.used_capacity_units}</td>
          </tr>
      )
    }
  ) : null;



  const handleAttachCancel = () => {}





  return (
    <Container fluid className='content_root' id='configure-container-id'>
      <Row>
            <Col>
              <div className='device_card' data-testid='app-server-card' id='app-server-card-id' style={{height: '336px'}}>
                <div className='config-host' data-testid='config-host' style={{ position:'sticky'}}>
                  
                </div>
                <div className='table-div' data-testid='table-div-id' style={{ maxHeight: '300px', overflowY: 'auto' }}>
                 <Table variant="dark" style={{fontFamily: 'Samsung sharp sons'}}>
                  <thead>
                    <tr>
                      {lmdTableHeader.map((item) => (
                        <th key={item} className='cofig-row'>{item}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody style={{ maxHeight: '160px', overflowY: 'auto' }}>
                    {lmdTable}        
                    <tr>
                      <td className='cofig-row'>
                        <Button variant="outline-light" size="sm" onClick={handleAttachMemoryToggle} data-testid="attach-id">
                          <img src={AddIcon} alt='add-Icon'width="30" height="auto" style={{objectFit: "cover"}} />
                        </Button>
                      </td>
                      <td className='cofig-row'></td>
                      <td className='cofig-row'></td>
                      <td className='cofig-row'></td>
                      <td className='cofig-row'></td>
                      <td className='cofig-row'></td>
                    </tr>
                  </tbody>
                 </Table>
                </div>
                {showAttach && (<AttachMemory onSave={handleAttach} onCancel={handleAttachCancel} show={showAttach} availableLMDs={availableLMDs} data-testid='attach-memory-modal'/>)}
              </div>
            </Col>
        </Row>
        <Row>
          <Col>
            <div className='device_card memoboxTable' data-testid='memoboxTable-id'>
              <div style={{marginTop: '16px'}} data-testid='cmmd-card-id' id='cmmd-card-id'>
                <Row>
                  <Col sm={8} md={8} lg={8}>
                    <div className='config-host'>
                      
                    </div>
                  </Col>
                </Row>
                <div className='table-div' data-testid='table-div-id' style={{ maxHeight: '300px', overflowY: 'auto' }}>
                  
                </div>
              </div>
              
            </div>
          </Col>
      </Row>
    </Container>
  )
}

export default Configure