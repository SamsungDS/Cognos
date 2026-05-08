import { useEffect, useState } from "react";
import { Modal, Button, Form, Spinner, Alert } from 'react-bootstrap';
import { DynamicField } from "./dynamicField";
import { fetchData } from "../../constant";
import * as constants from '../../../src/constant';
import "../job/createJobDialog.css"
import "../../pages/jobs.css"

export function DynamicFormModal({ config, isOpen, onClose, onSuccess }) {
    const apiEndpoint = constants.Configs.api_endpoint;
    const { title, endpoint, fields } = config;
    const [jobStatus, setJobStatus] = useState(null);

    // build initial state from field_name keys
    const initState = () => 
        fields.reduce((acc, f) => ({...acc, [f.field_name]: ""}), {});

    const [formData, setFormData] = useState(initState);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // reset form state
    useEffect(() => {
        setFormData(initState());
        setError(null);
    }, [config]);

    const handleChange = (field_name, value) =>
        setFormData((prev) => ({ ...prev, [field_name]: value }));
    
    const handleSubmit = async () => {
        setLoading(true);
        setError(null);
        
        // send API request to CAL and get response
        try {
            const res = await fetch(`${apiEndpoint}${endpoint}`, {
              method: "POST",
              headers: new Headers({
                'Access-Control-Allow-Origin':'*',
                'accept': 'application/json',
                'content-type': 'application/json'
              }),
              body: JSON.stringify(formData)
            });
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            const data = await res.json();
            setJobStatus(data?.status);
            onSuccess?.(data);
            setFormData(initState());
            onClose();
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleClose = () => {
        setFormData(initState());
        setError(null);
        onClose();
    };

    return (
        <Modal show={isOpen} onHide={handleClose} centered className="job-config-modal" backdrop="static" size="xl">
            <Modal.Header closeButton>
                <Modal.Title style={{color: "white"}}>Configure Job: {title}</Modal.Title>
            </Modal.Header>

            <Modal.Body className="job-modal-body">
                {error && (
                    <Alert variant="danger" onClose={() => setError(null)} dismissible>
                        {error}
                    </Alert>
                )}
                <Form>
                    {fields.map((field) => (
                        <DynamicField
                            key={field.field_name}
                            field={field}
                            value={formData[field.field_name]}
                            onChange={handleChange}
                        />
                    ))}
                </Form>
            </Modal.Body>

            <Modal.Footer>
                <Button variant="secondary" onClick={handleClose} disabled={loading}>
                    Cancel
                </Button>

                <Button variat="primary" onClick={handleSubmit} disabled={loading}>
                    {loading
                        ? <><Spinner animation="border" size="sm" className="me-2" />Launching...</>
                        : "Launch Job"
                    }

                </Button>
            </Modal.Footer>

        </Modal>
    );
}