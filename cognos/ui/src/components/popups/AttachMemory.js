import React, { useState} from 'react';
import Button from 'react-bootstrap/Button';
import { Form, Container, Row, Col } from 'react-bootstrap';
import Modal from 'react-bootstrap/Modal';
import 'rc-slider/assets/index.css';
import './MemoryPopup.css';

const AttachMemory = ({ show, onSave, onCancel, availableLMDs }) => {
    const [logicalMemoryDevice, setLogicalMemoryDevice] = useState('');
    const [memoryMode, setMemoryMode] = useState('');
    const [lmdCapacity, setlmdCapacity] = useState();
    const [hostMemoryAddress, setHostMemoryAddress] = useState();
    const [advancedMemSettings, setAdvancedMemSettings] = useState(false);

    const handleAdvancedMemSettings = () => {
        setAdvancedMemSettings(!advancedMemSettings)
    }

    const handleAttach = () => {
        const formData = {
        dev_name: logicalMemoryDevice,
        host_memory_address: hostMemoryAddress,
        lmdCapacity,
        };
        onSave(formData);
        setLogicalMemoryDevice('');
        setHostMemoryAddress('');
        setlmdCapacity('');
    }
    const options = availableLMDs ? availableLMDs.map((item) => (
        <option key={item} value={item}>{item}</option>)): [];
    
    return (<div>
        <Modal show={show} onHide={onCancel} className='custom-modal' id='attach-modal-id' data-testid='attach-memory-modal'>
            <Modal.Header closeButton closeVariant="white">
                <Modal.Title>Attach Memory</Modal.Title>
            </Modal.Header>
            <Modal.Body>
                <Form>
                    <Container>
                        <Row>
                            <Col xs={6} md={6}>
                                <Form.Group className="mb-3" controlId="logicalMemoryDevice">
                                    <Form.Label>Select CXL Device</Form.Label>
                                    <Form.Select
                                        value={logicalMemoryDevice}
                                        onChange={(e) => setLogicalMemoryDevice(e.target.value)}>
                                        <option>Select CXL Device</option> 
                                        {options}
                                    </Form.Select>
                                </Form.Group>
                            </Col>
                            <Col xs={6} md={6}>
                               <Form.Group className="mb-3" controlId="memoryMode">
                                    <Form.Label>Memory Mode</Form.Label>
                                    <Form.Select
                                        value={memoryMode}
                                        onChange={(e) => setMemoryMode(e.target.value)}>
                                        <option value="direct">Direct</option>
                                    </Form.Select>
                                </Form.Group>
                            </Col>
                        </Row>
                        <Row>
                            <Col xs={12} md={12}>
                                <Button onClick={handleAdvancedMemSettings} style={{color: 'white'}} data-testid='Advanced Memory Settings'>+ Advanced Memory Settings</Button>
                                {advancedMemSettings && <Form.Group className="mb-3" controlId="hostMomoryAddress">
                                    <Form.Label>start offset</Form.Label>
                                    <Form.Control
                                        type="text"
                                        placeholder="start offset"
                                        value={hostMemoryAddress}
                                        onChange={(e) => setHostMemoryAddress(e.target.value)}
                                        />
                                </Form.Group>}
                            </Col>
                        </Row>
                    </Container>
                </Form>
            </Modal.Body>
            <Modal.Footer>
                <Button variant='secondary' onClick={onCancel} data-testid='attach-memory-cancel-button'>
                    Cancel
                </Button>
                <Button variant='primary' onClick={handleAttach}>
                    Attach
                </Button>
            </Modal.Footer>
        </Modal>
    </div>)
}
export default AttachMemory;