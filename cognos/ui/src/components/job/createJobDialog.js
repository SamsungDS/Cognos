import React, { useState, useEffect } from 'react';
import { Modal, Button, Container, Row, Col, Form } from 'react-bootstrap';
import '../../pages/jobs.css';
import './createJobDialog.css';
import { Configs } from '../../constant';
import { LoadingSpinner, validateForm } from '../../utils/jobs-utils';

// istanbul ignore next
const apiService = {
  createSLA: async (slaConfig) => {
    try {
      const response = await fetch(`${Configs.api_endpoint}/set_app_sla`, {
        mode: "cors",
        method: 'POST',
        headers: {
          "Content-Type": "application/json",
          accept: "application/json",
          "Access-Control-Allow-Origin": "*",
        },
        body: JSON.stringify(slaConfig)
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error creating SLA:', error);
      throw error;
    }
  }
};

// istanbul ignore next
const CreateJobDialog = ({ isOpen, onClose, onJobCreated }) => {
  // Form State
  const [formData, setFormData] = useState({
    app_pid: '',
    app_name: '',
    server_name: '',
    avg_latency_ns: '',
    throughput_ops_per_sec: '',
    targetread_p99_latency: '',
    targetwrite_p99_latency: '',
  });

  // UI State
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState({
    submitting: false
  });
  const [apiError, setApiError] = useState(null);

  // Load hosts when modal opens
  useEffect(() => {
    if (!isOpen) return;
  }, [isOpen]);

  const handleInputChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));

    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }));
    }

    if (apiError) {
      setApiError(null);
    }
  };

  const handleStartTuning = async () => {
    const formErrors = validateForm(formData);

    if (Object.keys(formErrors).length > 0) {
      setErrors(formErrors);
      return;
    }

    setLoading(prev => ({ ...prev, submitting: true }));
    setApiError(null);

    try {
      // Prepare SLA configuration payload
      const slaConfig = {
        app_pid: parseInt(formData.app_pid),
        app_name: formData.app_name,
        server_name: formData.server_name,
        avg_latency_ns: parseFloat(formData.avg_latency_ns),
        throughput_ops_per_sec: parseFloat(formData.throughput_ops_per_sec),
        targetread_p99_latency: parseFloat(formData.targetread_p99_latency),
        targetwrite_p99_latency: parseFloat(formData.targetwrite_p99_latency),
      };

      // Call API to create SLA
      const result = await apiService.createSLA(slaConfig);

      // Pass the result back to parent component
      onJobCreated(result);

      // Close modal after success
      setTimeout(() => {
        onClose();
        resetForm();
      }, 1000);
    } catch (error) {
      console.error('Failed to create SLA:', error);
      setApiError('Failed to create SLA. Please try again.');
    } finally {
      setLoading(prev => ({ ...prev, submitting: false }));
    }
  };

  const resetForm = () => {
    setFormData({
      app_pid: '',
      app_name: '',
      server_name: '',
      avg_latency_ns: '',
      throughput_ops_per_sec: '',
      targetread_p99_latency: '',
      targetwrite_p99_latency: '',
    });
    setErrors({});
    setApiError(null);
  };

  const handleClose = () => {
    onClose();
    resetForm();
  };

  if (!isOpen) return null;

  return (
    <Modal
      show={true}
      onHide={handleClose}
      size="xl"
      centered
      className="job-config-modal"
      backdrop="static"
    >
      <Modal.Body className="job-modal-body">
        <Container fluid className="p-0">
          {/* API Error Alert */}
          {apiError && (
            <div className="alert alert-danger mb-3" role="alert">
              {apiError}
            </div>
          )}

          {/* SLA Configuration */}
          <div className="config-card mb-3">
            <div className="config-header">
              <div className="d-flex">
                <h2 className="config-title">
                  Create SLA
                </h2>
              </div>
            </div>
            <div className="config-body">
              <Row className="g-4">
                {/* Application PID */}
                <Col xs={12} md={6} lg={4}>
                  <Form.Group>
                    <Form.Label className="form-label-custom">
                      Application PID <span className="text-danger">*</span>
                    </Form.Label>
                    <Form.Control
                      type="number"
                      value={formData.app_pid}
                      onChange={(e) => handleInputChange("app_pid", e.target.value)}
                      placeholder="e.g. 1234"
                      className={`form-control-custom ${errors.app_pid ? 'is-invalid-custom' : ''}`}
                    />
                    {errors.app_pid && (
                      <div className="error-message">{errors.app_pid}</div>
                    )}
                  </Form.Group>
                </Col>

                {/* Application Name */}
                <Col xs={12} md={6} lg={4}>
                  <Form.Group>
                    <Form.Label className="form-label-custom">
                      Application Name <span className="text-danger">*</span>
                    </Form.Label>
                    <Form.Control
                      type="text"
                      value={formData.app_name}
                      onChange={(e) => handleInputChange("app_name", e.target.value)}
                      placeholder="e.g. CX03"
                      className={`form-control-custom ${errors.app_name ? 'is-invalid-custom' : ''}`}
                    />
                    {errors.app_name && (
                      <div className="error-message">{errors.app_name}</div>
                    )}
                  </Form.Group>
                </Col>

                {/* Server Name  */}
                <Col xs={12} md={6} lg={4}>
                  <Form.Group>
                    <Form.Label className="form-label-custom">
                      Server Name <span className="text-danger">*</span>
                    </Form.Label>
                    <Form.Control
                      type="text"
                      value={formData.server_name}
                      onChange={(e) => handleInputChange("server_name", e.target.value)}
                      placeholder="e.g. prod-server-01"
                      className={`form-control-custom ${errors.server_name ? 'is-invalid-custom' : ''}`}
                    />
                    {errors.server_name && (
                      <div className="error-message">{errors.server_name}</div>
                    )}
                  </Form.Group>
                </Col>

                {/* Average Latency */}
                <Col xs={12} md={6} lg={4}>
                  <Form.Group>
                    <Form.Label className="form-label-custom">
                      Avg Latency (ns) <span className="text-danger">*</span>
                    </Form.Label>
                    <Form.Control
                      type="number"
                      step="0.01"
                      value={formData.avg_latency_ns}
                      onChange={(e) => handleInputChange("avg_latency_ns", e.target.value)}
                      placeholder="e.g. 5500"
                      className={`form-control-custom ${errors.avg_latency_ns ? 'is-invalid-custom' : ''}`}
                    />
                    {errors.avg_latency_ns && (
                      <div className="error-message">{errors.avg_latency_ns}</div>
                    )}
                  </Form.Group>
                </Col>

                {/* Throughput */}
                <Col xs={12} md={6} lg={4}>
                  <Form.Group>
                    <Form.Label className="form-label-custom">
                      Throughput (ops/sec) <span className="text-danger">*</span>
                    </Form.Label>
                    <Form.Control
                      type="number"
                      step="0.01"
                      value={formData.throughput_ops_per_sec}
                      onChange={(e) => handleInputChange("throughput_ops_per_sec", e.target.value)}
                      placeholder="e.g. 1000"
                      className={`form-control-custom ${errors.throughput_ops_per_sec ? 'is-invalid-custom' : ''}`}
                    />
                    {errors.throughput_ops_per_sec && (
                      <div className="error-message">{errors.throughput_ops_per_sec}</div>
                    )}
                  </Form.Group>
                </Col>

                {/* Target Read P99 Latency */}
                <Col xs={12} md={6} lg={4}>
                  <Form.Group>
                    <Form.Label className="form-label-custom">
                      Target Read P99 Latency (ns) <span className="text-danger">*</span>
                    </Form.Label>
                    <Form.Control
                      type="number"
                      step="0.01"
                      value={formData.targetread_p99_latency}
                      onChange={(e) => handleInputChange("targetread_p99_latency", e.target.value)}
                      placeholder="e.g. 8000"
                      className={`form-control-custom ${errors.targetread_p99_latency ? 'is-invalid-custom' : ''}`}
                    />
                    {errors.targetread_p99_latency && (
                      <div className="error-message">{errors.targetread_p99_latency}</div>
                    )}
                  </Form.Group>
                </Col>

                {/* Target Write P99 Latency  */}
                <Col xs={12} md={6} lg={4}>
                  <Form.Group>
                    <Form.Label className="form-label-custom">
                      Target Write P99 Latency (ns) <span className="text-danger">*</span>
                    </Form.Label>
                    <Form.Control
                      type="number"
                      step="0.01"
                      value={formData.targetwrite_p99_latency}
                      onChange={(e) => handleInputChange("targetwrite_p99_latency", e.target.value)}
                      placeholder="e.g. 9000"
                      className={`form-control-custom ${errors.targetwrite_p99_latency ? 'is-invalid-custom' : ''}`}
                    />
                    {errors.targetwrite_p99_latency && (
                      <div className="error-message">{errors.targetwrite_p99_latency}</div>
                    )}
                  </Form.Group>
                </Col>
              </Row>
            </div>
          </div>

          {/* Control Panel */}
          <div className="control-panel">
            <div className="control-panel-body">
              <div className="d-flex flex-column flex-sm-row gap-3 align-items-center justify-content-end">
                <Button
                  onClick={handleClose}
                  variant="secondary"
                  className="btn-custom btn-cancel"
                  disabled={loading.submitting}
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleStartTuning}
                  disabled={loading.submitting}
                  variant="primary"
                  className="btn-custom btn-submit"
                >
                  {loading.submitting ? (
                    <LoadingSpinner />
                  ) : (
                    "Submit SLA"
                  )}
                </Button>
              </div>
            </div>
          </div>
        </Container>
      </Modal.Body>
    </Modal>
  );
};

export default CreateJobDialog;