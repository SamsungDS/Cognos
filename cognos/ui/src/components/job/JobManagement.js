import React, { useState } from "react";
import { Container, Button, Table } from "react-bootstrap";
import CreateJobDialog from "./createJobDialog";
import "../../pages/jobs.css";
import { JobRow, EmptyState } from "../../utils/jobs-utils";

// Main Job Management Component
const JobManagement = () => {
  // Jobs State
  const [jobs, setJobs] = useState([
    {
      id: 1749801058815,
      name: "host-002",
      type: "tier",
      status: "running",
      created: "2024-06-05 10:30",
      dramNumaNode: "1",
      cxlNumaNode: "0",
      aggregate: "LOW",
      applicationPID: "23567",
      applicationName: "Cx045",
    },
    {
      id: 1749801058816,
      name: "host-003",
      type: "migrate",
      status: "completed",
      created: "2024-06-05 09:15",
      aggregate: "LOW",
      source: "1",
      destination: "2",
      applicationPID: "23567",
      applicationName: "Cx045",
    },
    {
      id: 1749801058820,
      name: "host-001",
      type: "tier",
      status: "failed",
      created: "2024-06-05 08:45",
      dramNumaNode: "1",
      cxlNumaNode: "0",
      aggregate: "LOW",
      applicationPID: "23567",
      applicationName: "Cx045",
    },
  ]);

  // Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Handlers
  // istanbul ignore next
  const handleDeleteJob = (jobId) => {
    setJobs((prevJobs) => prevJobs.filter((job) => job.id !== jobId));
  };
  // istanbul ignore next
  const handleJobCreated = (newJob) => {
    setJobs((prevJobs) => [newJob, ...prevJobs]); // Add to beginning of array
    setShowCreateModal(false);
  };
  // istanbul ignore next
  const openCreateModal = () => {
    setShowCreateModal(true);
  };
  // istanbul ignore next
  const closeCreateModal = () => {
    setShowCreateModal(false);
  };

  return (
    <div>
      <Container fluid className="p-4">
        {/* Page Header */}
        <div className="d-flex justify-content-between align-items-center mb-4">
          <div>
            <h1 className="auto-tier-heading custom-tracking-wider">
              Job Management
            </h1>
            <p className="custom-text-gray-500 mt-1">
              Manage SCMC job configuration and monitor their status
            </p>
          </div>
          <Button
            variant="primary"
            onClick={openCreateModal}
            className="custom-create-btn d-flex align-items-center gap-2 fw-medium"
          >
            Create Job
          </Button>
        </div>

        {/* Jobs Table */}
        <div className="custom-table-container">
          {jobs.length > 0 ? (
            <Table responsive className="custom-table">
              {/* Table Header */}
              <thead>
                <tr>
                  <th className="text-center custom-th">Job ID</th>
                  <th className="text-center custom-th">Host Name</th>
                  <th className="text-center custom-th">Type</th>
                  <th className="text-center custom-th">Status</th>
                  <th className="text-center custom-th">Created</th>
                  <th className="text-center custom-th">Actions</th>
                </tr>
              </thead>
              {/* Table Body */}
              <tbody className="custom-tbody">
                {jobs.map((job) => (
                  <JobRow key={job.id} job={job} onDelete={handleDeleteJob} />
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState />
          )}
        </div>

        {/* Create Job Modal */}
        <CreateJobDialog
          isOpen={showCreateModal}
          onClose={closeCreateModal}
          onJobCreated={handleJobCreated}
        />
      </Container>
    </div>
  );
};

export default JobManagement;