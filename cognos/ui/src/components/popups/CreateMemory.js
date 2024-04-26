import React, { useState } from 'react';
import Button from 'react-bootstrap/Button';
import { Form, Container, Row, Col } from 'react-bootstrap';
import Modal from 'react-bootstrap/Modal';
import Slider from 'rc-slider';
import 'rc-slider/assets/index.css';
import './MemoryPopup.css';



function CreateMemory({ onCancel, onSave, show }) {
  const [logicalMemoryDevice, setLogicalMemoryDevice] = useState('');
  const [hostMemoryAddress, setHostMemoryAddress] = useState('');
  const [memoryType, setMemoryType] = useState('CMMD');
  const [memoryMode, setMemoryMode] = useState('Direct');
  const [pool, setPool] = useState('');
  const [memoryAllocation, setMemoryAllocation] = useState(0);
  const [isPoolFlag, setIsPoolFlag] = useState(false);

  const handleIsPoolChange = () => {
    setIsPoolFlag(!isPoolFlag)
  }

  const handleMemoryChange = (value) => {
    setMemoryAllocation(value);
  };

  const handleSaveClick = () => {
    // Create an object with the form data
    const formData = {
      logicalMemoryDevice,
      hostMemoryAddress,
      memoryType,
      memoryMode,
      pool: pool || 'Default Pool',
      memoryAllocation,
      isPoolFlag,
    };

    // Call the onSave callback with the form data
    onSave(formData);

    setLogicalMemoryDevice('');
    setHostMemoryAddress('');
    setMemoryType('CMMD');
    setMemoryMode('Direct');
    setPool('');
    setMemoryAllocation(0);
 
    console.log('Memory successfully created!')
  };

  return (
    <div>
      <Modal show={show} onHide={onCancel} className='custom-modal' id='create-mem-modal-id'>
        <Modal.Header closeButton closeVariant="white">
          <Modal.Title>Create Logical Memory Device</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form>
            <Container>
                <Row>
                    <Col xs={12} md={12}>
                        <Form.Group className="mb-3" controlId="logicalMemoryDevice">
                            <Form.Label>Logical Memory Device</Form.Label>
                            <Form.Control
                                type="text"
                                placeholder="Logical Memory Device"
                                value={logicalMemoryDevice}
                                onChange={(e) => setLogicalMemoryDevice(e.target.value)}
                                autoFocus
                            />
                        </Form.Group>
                    </Col>

                </Row>
                <Row>
                    <Col xs={12} md={12}>
                          <Form.Group className="mb-3" controlId="memorytype">
                            <Form.Label>Memory Type</Form.Label>
                            <Form.Select
                                value={memoryType}
                                onChange={(e) => setMemoryType(e.target.value)}>
                                <option value="CMMD">CMMD</option>
                            </Form.Select>
                          </Form.Group>
                    </Col>
                </Row>
                <Row>
                  <Col xs={6} md={6}>
                    <Form.Group className="mb-3" controlId="ispool">
                      <Form.Label>isPool</Form.Label>
                      <Form.Check 
                        type='checkbox'
                        checked={isPoolFlag}
                        onChange={handleIsPoolChange}
                      />
                    </Form.Group>
                  </Col>
                  <Col xs={6} md={6}>
                          <Form.Group className="mb-3" controlId="pool">
                            <Form.Label>Pool</Form.Label>
                            <Form.Select
                                value={pool}
                                onChange={(e) => setPool(e.target.value)}
                                disabled={isPoolFlag}
                            >
                            <option>Select existing pool</option>
                            <option value="Pool-1"> Pool-1</option>
                            <option value="Pool-2">Pool-2</option>
                          </Form.Select>
                        </Form.Group>
                    </Col>
                </Row>
                <Row>
                    <Col xs={12} md={12}>
                        <Form.Group className='mb-3' controlId='memory'>
                            <Form.Label>Memory Allocation {memoryAllocation} GB</Form.Label>
                            <Slider
                                value={memoryAllocation}
                                onChange={handleMemoryChange}
                                min={128}
                                max={256}
                                step={128}
                            />
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span>128 GB</span>
                                <span>256 GB</span>
                            </div>
                        </Form.Group>
                    </Col>
                </Row>
            </Container>
          </Form>
        </Modal.Body>
        <Modal.Footer>
          <Button variant='secondary' onClick={onCancel}>
            Cancel
          </Button>
          <Button variant='primary' onClick={handleSaveClick}>
            Create
          </Button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}

export default CreateMemory;