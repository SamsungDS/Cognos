import React, { useState, useEffect } from "react";
import { Container, Button, Table } from "react-bootstrap";
import CreateJobDialog from "./createJobDialog";
import "../../pages/jobs.css";
import { JobRow, EmptyState, jobApiService, columnHeader } from "../../utils/jobs-utils";

// Main Job Management Component
const JobManagement = () => {
  // Jobs State
  const [jobs, setJobs] = useState([]);

  // Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Fetch jobs on component mount
  useEffect(() => {
    fetchJobs();
  }, []);

  // updates every 5 seconds
  // istanbul ignore next
  useEffect(() => {
    const interval = setInterval(() => {
      if (!showCreateModal) {      
        fetchJobs(true); // Silent refresh (no loading state)
      }
    }, 5000); // 5 seconds

    return () => clearInterval(interval);
  }, [showCreateModal]);

  // Fetch jobs from API
  // istanbul ignore next
  const fetchJobs = async (silent = false) => {
    try {
      const data = await jobApiService.getAllJobs();

      // Handle different response formats
      const jobsArray = Array.isArray(data) ? data : (data.jobs || data.data || []);

      setJobs(jobsArray);
    } catch (err) {
      console.error('Failed to fetch jobs:', err);
    }
  };

  // Handlers
  // istanbul ignore next
  const handleDeleteJob = (jobId) => {
    setJobs((prevJobs) => prevJobs.filter((job) => job.id !== jobId));
  };

  // Handle new job creation
  // istanbul ignore next
  const handleJobCreated = (newJob) => {
    setJobs(prevJobs => [newJob, ...prevJobs]);
    setShowCreateModal(false);

    // refresh from server to ensure sync
    fetchJobs(true);
  };

  // Modal handlers
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
              Application View
            </h1>
            <p className="custom-text-gray-500 mt-1">
              Manage SCMC SLA configuration and monitor their status
            </p>
          </div>
          <Button         
            onClick={openCreateModal}
            className="custom-create-btn d-flex align-items-center gap-2 fw-medium"
          >
            Create SLA
          </Button>
        </div>

        {/* Jobs Table */}
        <div className="custom-table-container">
          {jobs.length > 0 ? (
            <Table responsive className="custom-table">
              {/* Table Header */}
              <thead>
                <tr>
                  {columnHeader.map((head) => <th className="text-center custom-th" key={head}>{head}</th>)}                
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