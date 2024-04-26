import React, { useState, useEffect } from 'react';
import Button from 'react-bootstrap/Button';
import { Form, Container, Row, Col } from 'react-bootstrap';
import Modal from 'react-bootstrap/Modal';
import 'rc-slider/assets/index.css';
import './MemoryPopup.css';


const FreeMemoryModalPopup = ({show, rowData, onCancel, onUpdate, onDelete}) => {
    const [logicalMemoryDevice, setLogicalMemoryDevice] = useState('');
    const [memoryType, setMemoryType] = useState('');
    const [memoryMode, setMemoryMode] = useState('');
    
    useEffect(() => {
        setLogicalMemoryDevice(rowData.lmd || '');
        setMemoryType(rowData.mem_type || '');
        setMemoryMode(rowData.mem_mode);
      }, [rowData]);

    return (
    <Modal show={show} onHide={onCancel} className='custom-modal-free-memory' id='free-mem-modal-id'>
        <Modal.Body>
            <Form>
            <Container>
                 <Row>
                    <Col xs={12} md={12}>
                        <h5>Free Memory</h5>
                    </Col>
                </Row>
                <Row>
                    <Col xs={12} md={6}>
                    <Form.Group className="mb-3" controlId="logicalMemoryDevice">
                        <Form.Label>Logical Memory Device</Form.Label>
                        <Form.Control
                            type="text"
                            placeholder="Logical Memory Device"
                            value={logicalMemoryDevice}
                            onChange={(e) => setLogicalMemoryDevice(e.target.value)}
                            autoFocus
                            disabled
                        />
                    </Form.Group>
                    </Col>
                    <Col xs={6} md={6}>
                        <Form.Group className="mb-3" controlId="memorytype">
                        <Form.Label>Memory Type</Form.Label>
                        <Form.Select
                            value={memoryType || rowData.mem_type}
                            onChange={(e) => setMemoryType(e.target.value)}
                            disabled
                        >
                            <option value="CMMD">CMMD</option>
                        </Form.Select>
                    </Form.Group>
                    </Col>
                </Row>
                <Row>
                    <Col xs={6} md={6}>
                        <Form.Group className="mb-3" controlId="memorymode">
                            <Form.Label>Memory Mode</Form.Label>
                            <Form.Select
                                value={memoryMode || rowData.mem_mode}
                                onChange={(e) => setMemoryMode(e.target.value)}
                                disabled
                            >
                            <option value="Direct">Direct</option>
                            <option value="Shared">Shared</option>
                            </Form.Select>
                        </Form.Group>
                    </Col>
                </Row>
                <Row style={{marginTop:12}}>
                    <Col xs={2} md={2}>
                        <Button variant='secondary' onClick={onCancel}>
                            Cancel
                        </Button>
                    </Col>
                    <Col xs={4} md={4}>
                        <Button variant='danger' onClick={() => onDelete(rowData.lmd)} data-testid='free-memory-button'>
                            Free Memory
                        </Button>
                    </Col>
                </Row>
            </Container>
            </Form>
        </Modal.Body>
    </Modal>
    )
}

export default FreeMemoryModalPopup;