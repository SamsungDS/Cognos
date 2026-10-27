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

const Configure = ({testMode}) => {
  const apiEndpoint = constants.Configs.api_endpoint;
  const AVAILABLE_DEVICES = 'available_devices';
  const HOST_DEVICES_ENDPT_SUFFIX = 'host_devices';
  const MEMBOX_DEVICES_ENDPT_SUFFIX = 'devices';
  const [showAttach, setShowAttach] = useState(false);
  const [selectedValue, setSelectedValue] = useState('');
  const [loading, setLoading] = useState(false);
  
  const [selectorOptions, setSelectorOptions] = useState([
    { value: "Select Host", label: "Select Host" },
  ]);


  const [showDetachMemory, setShowDetachMemory] = useState(false);
  const [attachedRowData, setAttachedRowData] = useState({});
  
  // host w/ attached devices top table state variable
  const [attachedDevicesData, setAttachedDevicesData] = useState([{}]);

  // Device to attach to host
  const [logicalMemoryDevice, setLogicalMemoryDevice] = useState('');

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
  const { handleAttach } = useAttachHook(setMemboxData, setAttachedDevicesData, () => setShowAttach(false), selectedValue, apiEndpoint, logicalMemoryDevice);
  const { handleDetach } = useDetachHook(setMemboxData, setAttachedDevicesData, () => setShowDetachMemory(false), selectedValue, apiEndpoint, attachedRowData);

  useEffect(() =>{
    setSelectedValue(selectorOptions[0]);
    fetch(`${apiEndpoint}/hosts`, {
      mode: 'cors',
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'accept': 'application/json',
        'Access-Control-Allow-Origin':'*'
      },
    }).then(response => response.json())
    .then(data => setSelectorOptions(data))
    .catch(err => {console.log(err)});
  }, []);
  
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

  // istanbul ignore next
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
  // istanbul ignore next
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

  // istanbul ignore next
  const handleAttachClick = async () => {
    setLoading(true);
    try {
      await handleAttach();
    } catch (error) {
      console.error("Attach operation failed", error);
    } finally {
      setLoading(false);
    }
  };
  
  // istanbul ignore next
  const handleDetachClick = async () => {
    setLoading(true);
    try {
      await handleDetach();
    } catch (error) {
      console.error("Attach operation failed", error);
    } finally {
      setLoading(false);
    }
  };

  const attachedDevicesTable =  Array.isArray ? attachedDevicesData.map(
    (item) => {
        return (
          <tr key={item.dev_name}>
            <td className='cofig-row'>
              <Button variant="outline-light" size="sm" onClick={() => handleDetachMemoryToggle(item)} data-testid="detach-button" disabled={loading}>
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
    <Container fluid className="content_root" id="configure-container-id">
      <Row>
        <Col>
          <div
            className="device_card memory-box-overview-height"
            data-testid="memory-box-overview"
            id="memory-box-overview-id"
          >
            <h4 className="configure-heading">CONFIGURE</h4>
          </div>
        </Col>
      </Row>
      <Row>
        <Col>
          <div
            className="device_card"
            data-testid="app-server-card"
            id="app-server-card-id"
            style={{ height: "336px" }}
          >
            <div
              className="config-host"
              data-testid="config-host"
              style={{ position: "sticky" }}
            >
              <DropDown
                options={selectorOptions}
                onSelectChange={(selectedOption) =>
                  handleSelectChange(
                    selectedOption,
                    `${apiEndpoint}/${HOST_DEVICES_ENDPT_SUFFIX}`,
                    setAttachedDevicesData
                  )
                }
                title={constants.hostSelectorTitle}
                dropDownType="single"
                name="hostTable"
              />
            </div>
            <div
              className="table-div"
              data-testid="table-div-id"
              style={{ maxHeight: "300px", overflowY: "auto" }}
            >
              <Table
                variant="dark"
                style={{ fontFamily: "Samsung sharp sons" }}
              >
                <thead>
                  <tr>
                    {constants.attachedDevicesTableHeader.map((item) => (
                      <th key={item} className="cofig-row">
                        {item}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody style={{ maxHeight: "160px", overflowY: "auto" }}>
                  {attachedDevicesTable}
                  <tr>
                    <td className="cofig-row">
                      <Button
                        variant="outline-light"
                        size="sm"
                        onClick={handleAttachMemoryToggle}
                        data-testid="attach-id"
                        disabled={!testMode && selectedValue['value'] === 'Select Host'}
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
                    <td className="cofig-row"></td>
                    <td className="cofig-row"></td>
                    <td className="cofig-row"></td>
                    <td className="cofig-row"></td>
                    <td className="cofig-row"></td>
                  </tr>
                </tbody>
              </Table>
            </div>
            {showAttach && (
              <AttachMemory
                onSave={handleAttachClick}
                onCancel={handleAttachCancel}
                show={showAttach}
                availableLMDs={availableLMDs}
                selectedValue={selectedValue}
                logicalMemoryDevice={logicalMemoryDevice}
                setLogicalMemoryDevice={setLogicalMemoryDevice}
                data-testid="attach-memory-modal"
              />
            )}
            {showDetachMemory && (
              <DetachMemory
                show={showDetachMemory}
                rowData={attachedRowData}
                onCancel={handleDetachMemoryCancel}
                onDelete={handleDetachClick}
                selectedValue={selectedValue}
              />
            )}
          </div>
        </Col>
      </Row>
      <Row>
        <Col>
          <div
            className="device_card memoboxTable"
            data-testid="memoboxTable-id"
          >
            <div
              style={{ marginTop: "16px" }}
              data-testid="cmmd-card-id"
              id="cmmd-card-id"
            >
              <Row>
                <Col sm={8} md={8} lg={8}>
                  <div className="config-host">
                    <DropDown
                      options={constants.memboxSelectorOptions}
                      title={constants.memboxSelectorTitle}
                      onSelectChange={(selectedOption) =>
                        handleSelectChange(
                          selectedOption,
                          `${apiEndpoint}/${MEMBOX_DEVICES_ENDPT_SUFFIX}`,
                          setMemboxData
                        )
                      }
                      dropDownType="single"
                      name="membox"
                    />
                  </div>
                </Col>
              </Row>
              <div
                className="table-div"
                data-testid="table-div-id"
                style={{ maxHeight: "300px", overflowY: "auto" }}
              >
                <Table variant="dark" style={{ fontFamily: "Samsung" }}>
                  <thead>
                    <tr>
                      {constants.memboxTableHeader.map((item) => (
                        <th key={item} className="cmm-row">
                          {item}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody style={{ maxHeight: "160px", overflowY: "auto" }}>
                    {memBoxTable}
                  </tbody>
                </Table>
              </div>
            </div>
          </div>
        </Col>
      </Row>
    </Container>
  );
}

export default Configure