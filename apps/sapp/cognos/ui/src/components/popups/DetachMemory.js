import React from 'react';
import Button from 'react-bootstrap/Button';
import { Container, Row, Col } from 'react-bootstrap';
import Modal from 'react-bootstrap/Modal';
import './MemoryPopup.css';

const DetachMemory = ({show, rowData, onCancel, onDelete, selectedValue}) => {
    const host_name = selectedValue?.label;
    return (
        <div>
            <Modal show={show} onHide={onCancel} className='custom-modal' id='detach-mem-modal-id' data-testid='detach-memory-modal'>
                <Modal.Header closeButton closeVariant="white">
                    <Modal.Title>Detach Memory</Modal.Title>
                </Modal.Header>
                <Modal.Body>
                    <Container>
                        <Row>
                            <Col xs={12} md={12}>
                                <p>Are you sure you want to detach <strong>{rowData.dev_name}</strong> Memory Device from server with hostname as <strong>{host_name}</strong> ?</p>
                            </Col>
                        </Row>
                    </Container>
                </Modal.Body>
                <Modal.Footer>
                    <Button variant='secondary' onClick={onCancel} data-testid='cancel-detach-button'>
                        Cancel
                    </Button>
                    <Button variant='primary' onClick={() => onDelete(rowData.dev_name)} data-testid='detach-memory-cancel-button'>
                        Detach
                    </Button>
                </Modal.Footer>
            </Modal>
        </div>
    )
}
export default DetachMemory;