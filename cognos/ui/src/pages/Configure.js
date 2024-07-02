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

  const apiEndpoint = constants.Configs.api_endpoint;
  const LMDs = 'lmds';
  const AVAILABLE_lMDs = 'available_lmds';
  const AVAILABLE_DEVICES = 'available_devices';
  const HOST_LMDs = 'host_lmds';
  const HOST_DEVICES = 'host_devices';
  const MEMBOX_LMDs = 'membox_lmds';
  const [showAttach, setShowAttach] = useState(false);
  const [selectedValue, setSelectedValue] = useState('');
  const [showDetachMemory, setShowDetachMemory] = useState(false);
  const [attachedRowData, setAttachedRowData] = useState({});
  
  // host w/ attached devices top table state variable
  const [lmdData, setLmdData] = useState([{}]);

  // MemBox bottom table state variable
  const [memboxData, setMemboxData] = useState([{
    dev_name: "DEVX",
    dev_capacity: 50023929,
    dev_id: 99999999,
    dev_port: 100,
    hosts_attached: "Host 1"
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
    fetch(`${apiEndpoint}/devices`, {
      method: 'post',
      headers: new Headers({
        'Access-Control-Allow-Origin':'*',
        'accept': 'application/json',
        'content-type': 'application/json'
      }),
      body: JSON.stringify({
        "input": "cluster_id=CLUST1;command=ListDevices;FM_id=203;FM_endpoint=samsung.com"
      })
    })
      .then(response => response.json())
      .then(data => setMemboxData(data))
      .catch(err => {console.log(err)});
  },
  // eslint-disable-next-line react-hooks/exhaustive-deps 
  []);

  const getAvailableLMDS = async() => {
    
    try {
      const response = await fetch(`${apiEndpoint}/${AVAILABLE_DEVICES}`, {
        mode: 'cors',
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'accept': 'application/json',
          'Access-Control-Allow-Origin':'*'
        },
      });

      if (response.ok) {
        const data = await response.json();
        setAvailableLMDs(data);
      }
    } catch (error) {console.log(error)};
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

    try {
      const response = await fetch(`${apiEndpoint}`, {
          mode: 'cors',
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin':'*',
            'accept': 'application/json'
          },
          body: JSON.stringify(payload)
      });

      if (response.ok) {
        const data = await response.json();
        setData(data);
      }
    } catch(error) {console.log(error)};
  };

  const lmdTable =  Array.isArray ? lmdData.map(
    (item) => {
        return (
          <tr key={item.dev_name}>
            <td className='cofig-row'>
              <Button variant="outline-light" size="sm" onClick={() => handleDetachMemoryToggle(item)} data-testid="detach-button">
                <img src={constants.MinusIcon} alt='minus-icon' width="25" height="auto" /> 
              </Button>
            </td>
            <td className='cofig-row'>{item.dev_name}</td>
            <td className='cofig-row'>{item.status}</td>
            <td className='cofig-row'>{item.type}</td>
            <td className='cofig-row'>{item.mode} {item.capacity_units}</td>
            <td className='cofig-row'>{item.dev_capacity}</td>
          </tr>
      )
    }
  ) : null;

  const memBoxTable = Array.isArray ? memboxData.map((item) => {
    return (
      <tr key={item.dev_id}>
        <td className='cmm-row'>{item.dev_name}</td>
        <td className='cmm-row'>{item.dev_id}</td>
        <td className='cmm-row'>{item.dev_capacity}</td>
        <td className='cmm-row'>{item.dev_port}</td>
        <td className='cmm-row'>{item.hosts_attached}</td>
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
                    onSelectChange={(selectedOption) => handleSelectChange(selectedOption, `${apiEndpoint}/${HOST_DEVICES}`, setLmdData)}
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
                {showAttach && (<AttachMemory onSave={handleAttach} onCancel={handleAttachCancel} show={showAttach} availableLMDs={availableLMDs} selectedValue={selectedValue} data-testid='attach-memory-modal'/>)}
                {showDetachMemory && 
                (<DetachMemory 
                show={showDetachMemory}
                rowData={attachedRowData}
                onCancel={handleDetachMemoryCancel}
                onDelete={handleDetach}
                selectedValue={selectedValue}
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