import React, { useState, useEffect } from 'react';
import {Modal, Button, Container, Row, Col, Form} from 'react-bootstrap';
import '../../pages/jobs.css';
import './createJobDialog.css';

import { LoadingSpinner } from '../../utils/jobs-utils';


// Mock API Service
// istanbul ignore next
const mockApiService = {
  getHosts: async () => {
    await new Promise(resolve => setTimeout(resolve, 500));
    return [
      { id: 'host-001', name: 'host-001'},
      { id: 'host-002', name: 'host-002'},
      { id: 'host-003', name: 'host-003'},
      { id: 'host-004', name: 'host-004'}
    ];
  },

  getHostDetails: async (hostId) => {
    await new Promise(resolve => setTimeout(resolve, 300));
    return {
      id: hostId,
      aggregates: ['LOW', 'HIGH'],
      sources: ['0', '1', '3'],
      destinations: ['4', '5']
    };
  },

  saveConfiguration: async (config) => {
    await new Promise(resolve => setTimeout(resolve, 1000));
    return { success: true, configId: Date.now() };
  },

  toggleAutoTiering: async (isRunning, config) => {
    await new Promise(resolve => setTimeout(resolve, 800));
    return { success: true, status: isRunning ? 'stopped' : 'running' };
  }
};

// istanbul ignore next
const validateForm = (formData) => {
  const errors = {};

  if (!formData.selectedHost) errors.selectedHost = 'Host is required';
  if (!formData.type) errors.type = 'Job type is required';
  
  // Conditional validation based on job type
  const showDramCxl = ['tier', 'promote', 'demote'].includes(formData.type);
  const showSourceDest = formData.type === 'migrate';
  
  if (showDramCxl) {
    if (!formData.dramNumaNode) errors.dramNumaNode = 'Faster tier is required';
    if (!formData.cxlNumaNode) errors.cxlNumaNode = 'Slower tier is required';
  }
  
  if (showSourceDest) {
    if (!formData.source) errors.source = 'Source is required';
    if (!formData.destination) errors.destination = 'Destination is required';
  }
  if (!formData.applicationPID) errors.applicationPID= 'Application PID is required';
  if (!formData.applicationName) errors.applicationName = 'Application Name is required';
  if (!formData.aggregate) errors.aggregate = 'Aggressiveness Level is required';

  return errors;
};

const CreateJobDialog = ({ isOpen, onClose, onJobCreated }) => {
  // Form State
  const [formData, setFormData] = useState({
    selectedHost: '',
    dramNumaNode: '',
    cxlNumaNode: '',
    aggregate: '',
    source: '',
    destination: '',
    applicationPID: '',
    applicationName: '',
    type: ''
  });

  // UI State
  const [availableHosts, setAvailableHosts] = useState([]);
  const [hostDetails, setHostDetails] = useState(null);
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState({
    hosts: false,
    hostDetails: false,
    submitting: false
  });
  const typeList = [ 'tier', 'promote', 'demote', 'migrate'];
  
  // Load hosts when modal opens
  // istanbul ignore next
  useEffect(() => {
    if (!isOpen) return;
    
    const loadHosts = async () => {
      setLoading(prev => ({ ...prev, hosts: true }));
      try {
        const hosts = await mockApiService.getHosts();
        setAvailableHosts(hosts);
      } catch (error) {
        console.error('Failed to load hosts:', error);
      } finally {
        setLoading(prev => ({ ...prev, hosts: false }));
      }
    };

    loadHosts();
  }, [isOpen]);

  // Load host details when host changes
  // istanbul ignore next
  useEffect(() => {
    if (!formData.selectedHost) {
      setHostDetails(null);
      return;
    }
    // istanbul ignore next
    const loadHostDetails = async () => {
      setLoading(prev => ({ ...prev, hostDetails: true }));
      try {
        const details = await mockApiService.getHostDetails(formData.selectedHost);
        setHostDetails(details);
      } catch (error) {
        console.error('Failed to load host details:', error);
      } finally {
        setLoading(prev => ({ ...prev, hostDetails: false }));
      }
    };

    loadHostDetails();
  }, [formData.selectedHost]);

  // Handle form input changes
  // istanbul ignore next
  const handleInputChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }));
    }
    
    // Clear fields that become hidden when job type changes
    // istanbul ignore next
    if (field === 'type') {
      const showDramCxl = ['tier', 'promote', 'demote'].includes(value);
      const showSourceDest = value === 'migrate';
      // istanbul ignore next
      if (!showDramCxl) {
        setFormData(prev => ({ ...prev, dramNumaNode: '', cxlNumaNode: '' }));
        setErrors(prev => ({ ...prev, dramNumaNode: undefined, cxlNumaNode: undefined }));
      }
      
      if (!showSourceDest) {
        setFormData(prev => ({ ...prev, source: '', destination: '' }));
        setErrors(prev => ({ ...prev, source: undefined, destination: undefined }));
      }
    }
  };

  // Handle form submission
  // istanbul ignore next
  const handleStartTuning = async () => {
    const formErrors = validateForm(formData);
    
    if (Object.keys(formErrors).length > 0) {
      setErrors(formErrors);
      return;
    }

    setLoading(prev => ({ ...prev, submitting: true }));

    try {
      const result = await mockApiService.toggleAutoTiering(formData);

      if (result.success) {
        // Create job for parent component
        const selectedHost = availableHosts.find(host => host.id === formData.selectedHost);
        const newJob = {
          id: Date.now(),
          name: selectedHost?.name || formData.selectedHost,
          type: formData.type,
          dramNumaNode: formData.dramNumaNode,
          cxlNumaNode: formData.cxlNumaNode,
          aggregate: formData.aggregate,
          source: formData.source,
          destination: formData.destination,
          applicationPID: formData.applicationPID,
          applicationName: formData.applicationName,
          status: 'completed',
          created: new Date().toLocaleString('en-CA', { 
            year: 'numeric', 
            month: '2-digit', 
            day: '2-digit', 
            hour: '2-digit', 
            minute: '2-digit',
            hour12: false 
          }).replace(',', ''),
          config: { ...formData }
        };

        onJobCreated(newJob);

        // Auto close after success
        setTimeout(() => {
          onClose();
          resetForm();
        }, 2000);
      }
    } catch (error) {
      console.error('Failed to job configuration:', error);
    } finally {
      setLoading(prev => ({ ...prev, submitting: false }));
    }
  };

  // Reset form to initial state
  // istanbul ignore next
  const resetForm = () => {
    setFormData({
      selectedHost: '',
      dramNumaNode: '',
      cxlNumaNode: '',
      aggregate: '',
      source: '',
      destination: '',
      applicationPID: '',
      applicationName: '',
      type: ''
    });
    setErrors({});
    setHostDetails(null);
  };

  // Handle modal close
  // istanbul ignore next
  const handleClose = () => {
    onClose();
    resetForm();
  };

  // Determine which fields to show based on job type
  const showDramCxlFields = ['tier', 'promote', 'demote'].includes(formData.type);
  const showSourceDestFields = formData.type === 'migrate';

  if (!isOpen) return null;
  // istanbul ignore next
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
        {/* Host Configuration */}
        <div className="config-card mb-3">
          <div className="config-header">
            <div className="d-flex">
              <h2 className="config-title">
                SCMC Job Configuration
              </h2>
            </div>
          </div>
          <div className="config-body">
            <Row className="g-4">
              {/* Host Selection */}
              <Col xs={12} md={6} lg={4}>
                <Form.Group>
                  <Form.Label className="form-label-custom">
                    Select Host <span className="text-danger">*</span>
                  </Form.Label>
                  <div className="position-relative">
                    <Form.Select
                      value={formData.selectedHost}
                      onChange={(e) => handleInputChange("selectedHost", e.target.value)}
                      className={`form-select-custom ${errors.selectedHost ? 'is-invalid-custom' : ''}`}
                    >
                      <option value="">
                        {loading.hosts ? "Loading hosts..." : "Select a host..."}
                      </option>
                      {availableHosts.map((host) => (
                        <option key={host.id} value={host.id}>
                          {host.name}
                        </option>
                      ))}
                    </Form.Select>
                    {loading.hosts && (
                      <div className="loading-spinner-overlay">
                        <LoadingSpinner />
                      </div>
                    )}
                  </div>
                  {errors.selectedHost && (
                    <div className="error-message">{errors.selectedHost}</div>
                  )}
                </Form.Group>
              </Col>

              {/* Type */}
              <Col xs={12} md={6} lg={4}>
                <Form.Group>
                  <Form.Label className="form-label-custom">
                    Job Type <span className="text-danger">*</span>
                  </Form.Label>
                  <Form.Select
                    value={formData.type}
                    onChange={(e) => handleInputChange("type", e.target.value)}
                    className={`form-select-custom ${errors.type ? 'is-invalid-custom' : ''}`}
                  >
                    <option value="">Select type...</option>
                    {typeList?.map((typ) => (
                      <option key={typ} value={typ}>
                        {typ}
                      </option>
                    ))}
                  </Form.Select>
                  {errors.type && (
                    <div className="error-message">{errors.type}</div>
                  )}
                </Form.Group>
              </Col>

              {/* Application PID */}
              <Col xs={12} md={6} lg={4}>
                <Form.Group>
                  <Form.Label className="form-label-custom">
                    Application PID <span className="text-danger">*</span>
                  </Form.Label>
                  <Form.Control
                    type="text"
                    value={formData.applicationPID}
                    onChange={(e) => handleInputChange("applicationPID", e.target.value)}
                    placeholder="e.g. 1234"
                    className={`form-control-custom ${errors.applicationPID ? 'is-invalid-custom' : ''}`}
                  />
                  {errors.applicationPID && (
                    <div className="error-message">{errors.applicationPID}</div>
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
                    value={formData.applicationName}
                    onChange={(e) => handleInputChange("applicationName", e.target.value)}
                    placeholder="e.g. CX03"
                    className={`form-control-custom ${errors.applicationName ? 'is-invalid-custom' : ''}`}
                  />
                  {errors.applicationName && (
                    <div className="error-message">{errors.applicationName}</div>
                  )}
                </Form.Group>
              </Col>

              {/* CXL NUMA Node - Show for tiering, promote, demote */}
              {showDramCxlFields && (
                <Col xs={12} md={6} lg={4}>
                  <Form.Group>
                    <Form.Label className="form-label-custom">
                      Slower Tier <span className="text-danger">*</span>
                    </Form.Label>
                    <Form.Control
                      type="text"
                      value={formData.cxlNumaNode}
                      onChange={(e) => handleInputChange("cxlNumaNode", e.target.value)}
                      placeholder="e.g. 0"
                      className={`form-control-custom ${errors.cxlNumaNode ? 'is-invalid-custom' : ''}`}
                    />
                    {errors.cxlNumaNode && (
                      <div className="error-message">{errors.cxlNumaNode}</div>
                    )}
                  </Form.Group>
                </Col>
              )}

              {/* DRAM NUMA Node - Show for tiering, promote, demote */}
              {showDramCxlFields && (
                <Col xs={12} md={6} lg={4}>
                  <Form.Group>
                    <Form.Label className="form-label-custom">
                      Faster Tier <span className="text-danger">*</span>
                    </Form.Label>
                    <Form.Control
                      type="text"
                      value={formData.dramNumaNode}
                      onChange={(e) => handleInputChange("dramNumaNode", e.target.value)}
                      placeholder="e.g. 1"
                      className={`form-control-custom ${errors.dramNumaNode ? 'is-invalid-custom' : ''}`}
                    />
                    {errors.dramNumaNode && (
                      <div className="error-message">{errors.dramNumaNode}</div>
                    )}
                  </Form.Group>
                </Col>
              )}

              {/* Storage Configuration - Only show when host is selected */}
              {hostDetails && (
                <>
                  {/* Aggressiveness Level */}
                  <Col xs={12} md={6} lg={4}>
                    <Form.Group>
                      <Form.Label className="form-label-custom">
                        Aggressiveness Level <span className="text-danger">*</span>
                      </Form.Label>
                      <Form.Select
                        value={formData.aggregate}
                        onChange={(e) => handleInputChange("aggregate", e.target.value)}
                        className={`form-select-custom ${errors.aggregate ? 'is-invalid-custom' : ''}`}
                      >
                        <option value="">Select Level...</option>
                        {hostDetails.aggregates?.map((aggr) => (
                          <option key={aggr} value={aggr}>
                            {aggr}
                          </option>
                        ))}
                      </Form.Select>
                      {errors.aggregate && (
                        <div className="error-message">{errors.aggregate}</div>
                      )}
                    </Form.Group>
                  </Col>

                  {/* Source - Only show for Migrate_App */}
                  {showSourceDestFields && (
                    <Col xs={12} md={6} lg={4}>
                      <Form.Group>
                        <Form.Label className="form-label-custom">
                          Source <span className="text-danger">*</span>
                        </Form.Label>
                        <Form.Select
                          value={formData.source}
                          onChange={(e) => handleInputChange("source", e.target.value)}
                          className={`form-select-custom ${errors.source ? 'is-invalid-custom' : ''}`}
                        >
                          <option value="">Select source...</option>
                          {hostDetails.sources?.map((src) => (
                            <option key={src} value={src}>
                              {src}
                            </option>
                          ))}
                        </Form.Select>
                        {errors.source && (
                          <div className="error-message">{errors.source}</div>
                        )}
                      </Form.Group>
                    </Col>
                  )}

                  {/* Destination - Only show for Migrate_App */}
                  {showSourceDestFields && (
                    <Col xs={12} md={6} lg={4}>
                      <Form.Group>
                        <Form.Label className="form-label-custom">
                          Destination <span className="text-danger">*</span>
                        </Form.Label>
                        <Form.Select
                          value={formData.destination}
                          onChange={(e) => handleInputChange("destination", e.target.value)}
                          className={`form-select-custom ${errors.destination ? 'is-invalid-custom' : ''}`}
                        >
                          <option value="">Select destination...</option>
                          {hostDetails.destinations?.map((dest) => (
                            <option key={dest} value={dest}>
                              {dest}
                            </option>
                          ))}
                        </Form.Select>
                        {errors.destination && (
                          <div className="error-message">{errors.destination}</div>
                        )}
                      </Form.Group>
                    </Col>
                  )}
                </>
              )}
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
                  "Submit Job"
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