import React, { useState, useEffect} from 'react';
import { Button, Container, Row, Col, Table } from 'react-bootstrap';

import DropDown from '../components/DropDown';
import useAttachHook from '../customhooks/useAttachHook';
import useDetachHook from '../customhooks/useDetachHook';

import AttachMemory from '../components/popups/AttachMemory';
import DetachMemory from '../components/popups/DetachMemory';

import './configure.css';
import './metrics.css';
import * as constants from '../../src/constant';

export const getReadableStatus = (job) => {
  if (job.status === 'loading') {
    return "Rebooting Host";
  }
  return `${job.status}`;
};

const Configure = () => {

  const apiEndpoint = constants.Configs.data_endpoint;
  const LMDs = 'lmds';
  const AVAILABLE_lMDs = 'available_lmds';
  const HOST_LMDs = 'host_lmds';
  const MEMBOX_LMDs = 'membox_lmds';
  const [showAttach, setShowAttach] = useState(false);
  const [selectedValue, setSelectedValue] = useState('');
  const [showDetachMemory, setShowDetachMemory] = useState(false);
  const [attachedRowData, setAttachedRowData] = useState({});
  // used for top table
  const [lmdData, setLmdData] = useState([{
    lmd: 'D-1',
    host: 'Host 2',
    mem_type: 'CMMD',
    mem_mode: 'Direct',
    capacity: 128,
    capacity_units: 'GB',
    used_capacity: 0,
    used_capacity_units: 'GB'
  }]);
  // used for bottom table
  const [memboxData, setMemboxData] = useState([{
    lmd: 'D-1',
    mem_type: 'CMMD',
    mem_mode: 'Direct',
    capacity: 128,
    capacity_units: 'GB',
    used_capacity: 0,
    used_capacity_units: 'GB',
    status: 'loading',
    host: 'Host1'
  }]);
  const [availableLMDs, setAvailableLMDs] = useState([]);

  // Attach and Detach use hook
  const { handleAttach } = useAttachHook(setMemboxData, setLmdData, () => setShowAttach(false), selectedValue, apiEndpoint);
  const { handleDetach } = useDetachHook(setMemboxData, setLmdData, () => setShowDetachMemory(false), selectedValue, apiEndpoint);

  const statusImages = {
    "active": constants.ActiveLight,
    "unhealthy": constants.UnhealthyLight,
    "inactive": constants.InactiveLight,
    "loading": constants.LoadingGif,
    "ready": constants.ReadyLight,
  }

  useEffect(() => {
    fetch(`${apiEndpoint}//${LMDs}`, {
      method: 'get',
      headers: new Headers({
        'Access-Control-Allow-Origin':'*'
      })
    })
      .then(response => response.json())
      .then(data => setMemboxData(data));
  }, 
  // eslint-disable-next-line react-hooks/exhaustive-deps 
  []);

  const getAvailableLMDS = async() => {
    const response = await fetch(`${apiEndpoint}//${AVAILABLE_lMDs}`, {
      mode: 'cors',
      method: 'GET',
      headers: {'Content-Type': 'application/json', 'Access-Control-Allow-Origin':'*'},
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
  
  const handleDetachMemoryToggle = (item) => {
    setAttachedRowData(item)
    setShowDetachMemory(!showDetachMemory);
  }
  const handleAttachCancel = () => {
    handleAttachMemoryToggle();
  }
  const handleDetachMemoryCancel = () => {
    handleDetachMemoryToggle();
  }

  // Callback function to handle selection change
  const handleSelectChange = async (selectedOption, apiEndpoint, setData) => {
    setSelectedValue(selectedOption);

    const payload = { host: selectedOption['label'] };

    const response = await fetch(`${apiEndpoint}`, {
        mode: 'cors',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin':'*' },
        body: JSON.stringify(payload)
    });

    if (response.ok) {
      const data = await response.json();
      setData(data);
    }
};



  const lmdTable =  Array.isArray ? lmdData.map(
    (item) => {
        return (
          <tr key={item.lmd}>
            <td className='cofig-row'>
              <Button variant="outline-light" size="sm" onClick={() => handleDetachMemoryToggle(item)} data-testid="detach-button">
                <img src={constants.MinusIcon} alt='minus-icon' width="25" height="auto" /> 
              </Button>
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
  const memBoxTable = Array.isArray ? memboxData.map((item) => {
    return (
      <tr key={item.lmd}>
        <td className='cmm-row'>
          <img 
            src={statusImages[item.status]}
            alt='status-icon'
            width="25" 
            height="auto"
            title={item.status === 'unhealthy' ? 'failure: unable to allocate memory' : getReadableStatus(item.status)}
          />
        </td>
        <td className='cmm-row'>{item.lmd}</td>
        <td className='cmm-row'>{item.device_type}</td>
        <td className='cmm-row'>{item.capacity} {item.capacity_units}</td>
        <td className='cmm-row'>{item.memory_servers}</td>
      </tr>
    ) 
  }): null;



  return (
    <Container fluid className='content_root' id='configure-container-id'>
      <Row>
            <Col>
              <div className='device_card' data-testid='app-server-card' id='app-server-card-id' style={{height: '336px'}}>
                <div className='config-host' data-testid='config-host' style={{ position:'sticky'}}>
                  <DropDown options={constants.hostSelectorOptions} 
                    onSelectChange={(selectedOption) => handleSelectChange(selectedOption, `${apiEndpoint}//${HOST_LMDs}`, setLmdData)}
                    title={constants.hostSelectorTitle}
                    dropDownType="single"
                    name='hostTable'
                  />
                </div>
                <div className='table-div' data-testid='table-div-id' style={{ maxHeight: '300px', overflowY: 'auto' }}>
                 <Table variant="dark" style={{fontFamily: 'Samsung sharp sons'}}>
                  <thead>
                    <tr>
                      {constants.lmdTableHeader.map((item) => (
                        <th key={item} className='cofig-row'>{item}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody style={{ maxHeight: '160px', overflowY: 'auto' }}>
                    {lmdTable}        
                    <tr>
                      <td className='cofig-row'>
                        <Button variant="outline-light" size="sm" onClick={handleAttachMemoryToggle} data-testid="attach-id">
                          <img src={constants.AddIcon} alt='add-Icon'width="30" height="auto" style={{objectFit: "cover"}} />
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
                {showDetachMemory && 
                (<DetachMemory 
                show={showDetachMemory}
                rowData={attachedRowData}
                onCancel={handleDetachMemoryCancel}
                onDelete={handleDetach}
                />)}
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
                      <DropDown 
                        options={constants.memboxSelectorOptions}  
                        title={constants.memboxSelectorTitle}
                        onSelectChange={(selectedOption) => handleSelectChange(selectedOption, `${apiEndpoint}//${MEMBOX_LMDs}`, setMemboxData)}
                        dropDownType="single"
                        name='membox'
                      />
                    </div>
                  </Col>
                </Row>
                <div className='table-div' data-testid='table-div-id' style={{ maxHeight: '300px', overflowY: 'auto' }}>
                  <Table variant="dark" style={{fontFamily: 'Samsung'}}>
                    <thead>
                      <tr>
                        {constants.memboxTableHeader.map((item) => (
                          <th key={item} className='cmm-row'>{item}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody style={{ maxHeight: '160px', overflowY: 'auto' }}>
                      {memBoxTable}
                      <tr>                        
                        <td className='cmm-row'></td>
                        <td className='cmm-row'></td>
                        <td className='cmm-row'></td>
                        <td className='cmm-row'></td>
                        <td className='cmm-row'></td>
                      </tr>
                    </tbody>
                  </Table>
                </div>
              </div>
            </div>
          </Col>
      </Row>
    </Container>
  )
}

export default Configure