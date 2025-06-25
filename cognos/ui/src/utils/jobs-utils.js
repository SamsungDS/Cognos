import { Button, Badge, Form } from "react-bootstrap";
import "../pages/jobs.css";

// Constants
export const FORM_VALIDATION_RULES = {
  NUMA_NODE: /^\d+$/,
  POSITIVE_INTEGER: /^\d+$/,
  POSITIVE_NUMBER: /^\d+(\.\d+)?$/,
  PID: /^\d+$/, // Added PID validation pattern
  REQUIRED_FIELDS: {
    HOST: "selectedHost",
    DRAM_NUMA: "dramNumaNode",
    CXL_NUMA: "cxlNumaNode",
    AGGREGATE: "aggregate",
    SOURCE: "source",
    DESTINATION: "destination",
  },
  OPTIONAL_FIELDS: {
    APPLICATION_PID: "applicationPID", // Added optional fields section
  },
};

// Components
// istanbul ignore next
export const LoadingSpinner = () => (
  <div className="custom-spinner"></div>
);

// istanbul ignore next
export const ErrorMessage = ({ error, show = true }) => {
  if (!show || !error) return null;

  return <p className="mt-1 small custom-error-text d-flex align-items-center">{error}</p>;
};


// istanbul ignore next
export const FormField = ({
  label,
  value,
  onChange,
  error,
  disabled,
  type = "text",
  placeholder,
  helpText,
  required = false,
  children,
}) => (
  <div>
    <Form.Label className="custom-label">
      {label} {required && <span className="custom-required">*</span>}
    </Form.Label>
    {children || (
      <Form.Control
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={`custom-input ${error ? "custom-input-error" : ""} ${
          disabled ? "custom-input-disabled" : ""
        }`}
      />
    )}
    <ErrorMessage error={error} show={!disabled} />
    {helpText && <p className="mt-1 custom-help-text">{helpText}</p>}
  </div>
);

// Status Badge Component
export const StatusBadge = ({ status }) => {
  const statusStyles = {
    running: "custom-badge-running",
    completed: "custom-badge-completed",
    failed: "custom-badge-failed",
    pending: "custom-badge-pending",
  };

  const statusClass = statusStyles[status] || "custom-badge-default";

  return (
    <Badge
      className={`custom-badge-base ${statusClass} d-flex align-items-center gap-2`}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
};

const formatCustomTooltip = (job) => {
  return `App PID: ${job.applicationPID}\nApp Name: ${
    job.applicationName
  }\nAggressiveness level: ${job.aggregate}\n${
    job.dramNumaNode
      ? `Faster tier: ${job.dramNumaNode}\nSlower tier: ${job.cxlNumaNode}`
      : ""
  }\n${
    job.source ? `Source: ${job.source}\nDestination: ${job.destination}` : ""
  }`;
};
// Job Table Row Component
export const JobRow = ({ job, onDelete }) => (
  <tr title={formatCustomTooltip(job)}>
    <td className="custom-table-cell">
      <div className="small fw-medium text-white">{job.id}</div>
    </td>
    <td className="custom-table-cell">
      <div className="small fw-medium text-white">{job.name}</div>
    </td>
    <td className="custom-table-cell">
      <div className="small text-white">{job.type}</div>
    </td>
    <td className="custom-table-cell">
      <StatusBadge status={job.status} />
    </td>
    <td className="custom-table-cell">
      <div className="small text-white">{job.created}</div>
    </td>
    <td className="custom-table-cell">
      <Button
        variant="outline-danger"
        size="sm"
        onClick={() => onDelete(job.id)}
        className="custom-delete-btn"
        title="Delete Job"
      >
        Delete
      </Button>
    </td>
  </tr>
);

// Empty State Component
export const EmptyState = () => (
  <div className="text-center custom-empty-state">
    <h3 className="custom-text-gray-500 fw-medium mb-1">No jobs found</h3>
    <p className="custom-text-gray-500 small">
      Create a new job to get started
    </p>
  </div>
);
