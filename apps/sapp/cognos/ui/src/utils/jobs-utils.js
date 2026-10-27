import { Badge, Form } from "react-bootstrap";
import PropTypes from "prop-types";
import "../pages/jobs.css";
import { Configs } from "../constant";


export const columnHeader = [
  "App Name",
  "App PID",
  "Server node",
  "Target Throughput(ops / s)",
  "Target Read P99 Latency(us)",
  "Target Write P99 Latency(us)",
  "Status",
  "Message"
];

// Components

export const LoadingSpinner = () => <div className="custom-spinner"></div>;


export const ErrorMessage = ({ error, show = true }) => {
  if (!show || !error) return null;

  return (
    <p className="mt-1 small custom-error-text d-flex align-items-center">
      {error}
    </p>
  );
};


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
    good: "custom-badge-completed",
    degraded: "custom-badge-pending",
    device_degraded: "custom-badge-pending",
    failed: "custom-badge-failed"
  };

  const statusClass = statusStyles[status] || "custom-badge-default";

  return (
    <Badge
      className={`custom-badge-base ${statusClass} d-flex align-items-center gap-2`}
      style={{ margin: 0 }}
    >
      {status}
    </Badge>
  );
};
StatusBadge.propTypes = {
  status: PropTypes.string.isRequired,
};
// Job Table Row Component

export const JobRow = ({ job, onDelete }) => (
  <tr>
    <td className="custom-table-cell">
      <div className="small fw-medium text-white">{job.app_name}</div>
    </td>
    <td className="custom-table-cell">
      <div className="small fw-medium text-white">{job.app_pid}</div>
    </td>
    <td className="custom-table-cell">
      <div className="small fw-medium text-white">{job.server_name}</div>
    </td>
    <td className="custom-table-cell">
      <div className="small fw-medium text-white">{job.throughput_ops_per_sec}</div>
    </td>
    <td className="custom-table-cell">
      <div className="small fw-medium text-white">{job.targetread_p99_latency}</div>
    </td>
    <td className="custom-table-cell">
      <div className="small fw-medium text-white">{job.targetwrite_p99_latency}</div>
    </td>
    <td className="custom-table-cell" title={`data moved: ${job.data_moved}%`}>     
        <StatusBadge status={job.status} />
    </td>
    <td className="custom-table-cell">
      <div className="small fw-medium text-white">{job.message?.replaceAll('_', ' ')}</div>
    </td>
  </tr>
);
JobRow.propTypes = {
  job: PropTypes.shape({
    app_name: PropTypes.string.isRequired,
    app_pid: PropTypes.oneOfType([PropTypes.string, PropTypes.number])
      .isRequired,
    status: PropTypes.string.isRequired,
    server_name: PropTypes.string.isRequired,
    throughput_ops_per_sec: PropTypes.string.isRequired,
    targetread_p99_latency: PropTypes.string.isRequired,
    targetwrite_p99_latency: PropTypes.string.isRequired,
    data_moved: PropTypes.string,
    data_moved_percentage: PropTypes.number,
    message: PropTypes.string
  }).isRequired,
};
// Empty State Component
export const EmptyState = () => (
  <div className="text-center custom-empty-state">
    <h3 className="custom-text-gray-500 fw-medium mb-1">No apps found</h3>
    <p className="custom-text-gray-500 small">
      No apps currently being monitored, please register application
    </p>
  </div>
);
// API Service

export const jobApiService = {
  // Fetch all jobs
  getAllJobs: async () => {
    try {
      const response = await fetch(
        `${Configs.api_endpoint}/application_status`,
        {
          mode: "cors",
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            accept: "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error("Error fetching jobs:", error);
      throw error;
    }
  },
};

export const validateForm = (formData) => {
  const errors = {};

  if (!formData.app_pid) errors.app_pid = "Application PID is required";
  if (!formData.app_name) errors.app_name = "Application Name is required";
  if (!formData.avg_latency_ns)
    errors.avg_latency_ns = "Average Latency is required";
  if (!formData.throughput_ops_per_sec)
    errors.throughput_ops_per_sec = "Throughput is required";
  if (!formData.targetread_p99_latency)
    errors.targetread_p99_latency = "target read p99 latency is required";
  if (!formData.targetwrite_p99_latency)
    errors.targetwrite_p99_latency = "target write p99 latency is required";

  return errors;
};
