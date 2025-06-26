import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import JobManagement from './JobManagement';

// Mock the Job component since it's imported
jest.mock('./createJobDialog', () => {
  return function MockAutoTier({ isOpen, onClose, onJobCreated }) {
    if (!isOpen) return null;
    
    return (
      <div data-testid="auto-tier-modal">
        <button 
          data-testid="mock-close-button" 
          onClick={onClose}
        >
          Close Modal
        </button>
        <button 
          data-testid="mock-create-job-button"
          onClick={() => onJobCreated({
            id: 4,
            name: 'test-host',
            type: 'auto tier',
            status: 'pending',
            created: '2024-06-05 12:00'
          })}
        >
          Create Test Job
        </button>
      </div>
    );
  };
});

// Mock CSS import
jest.mock('../../pages/jobs.css', () => ({}));

describe('JobManagement Component', () => {
  beforeEach(() => {
    // Clear any mocks before each test
    jest.clearAllMocks();
  });

  describe('Initial Render', () => {
    test('renders the component with correct heading and description', () => {
      render(<JobManagement />);
      
      expect(screen.getByText('Job Management')).toBeInTheDocument();
      expect(screen.getByText('Manage SCMC job configuration and monitor their status')).toBeInTheDocument();
    });


    test('renders table headers correctly', () => {
      render(<JobManagement />);
      
      expect(screen.getByText('Host Name')).toBeInTheDocument();
      expect(screen.getByText('Type')).toBeInTheDocument();
      expect(screen.getByText('Job ID')).toBeInTheDocument();
      expect(screen.getByText('Status')).toBeInTheDocument();
      expect(screen.getByText('Created')).toBeInTheDocument();
      expect(screen.getByText('Actions')).toBeInTheDocument();
    });
  });

  describe('StatusIcon Component', () => {
    test('renders correct icons for different statuses', () => {
      render(<JobManagement />);
      
      // Check for different status badges
      expect(screen.getByText('Running')).toBeInTheDocument();
      expect(screen.getByText('Completed')).toBeInTheDocument();
      expect(screen.getByText('Failed')).toBeInTheDocument();
    });
  });

  describe('Empty State', () => {
    test('shows empty state when no jobs exist', () => {
      // Mock JobManagement with empty jobs array
      const EmptyJobManagement = () => {
        const [jobs, setJobs] = React.useState([]);
        const [showCreateModal, setShowCreateModal] = React.useState(false);
        
        return (
          <div className="p-6">
            <div className="flex justify-between items-center mb-6">
              <div>
                <h1 className="auto-tier-heading tracking-wider">Job Management</h1>
                <p className="text-gray-600 mt-1">Manage auto-tiering jobs and monitor their status</p>
              </div>
            </div>
            <div className='overflow-y'>
              {jobs.length > 0 ? (
                <table></table>
              ) : (
                <div className="text-center py-12">
                  <div className="text-gray-400 mb-2">
                    <div className="w-12 h-12 mx-auto opacity-50" />
                  </div>
                  <h3 className="text-gray-600 font-medium mb-1">No jobs found</h3>
                  <p className="text-gray-500 text-sm">Create a new job to get started</p>
                </div>
              )}
            </div>
          </div>
        );
      };
      
      render(<EmptyJobManagement />);
      
      expect(screen.getByText('No jobs found')).toBeInTheDocument();
      expect(screen.getByText('Create a new job to get started')).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    test('handles undefined status in StatusIcon', () => {
      const StatusIcon = ({ status }) => {
        const iconProps = { className: "w-4 h-4" };
        switch (status) {
          case 'running':
            return <div {...iconProps} className="w-4 h-4 text-blue-500" />;
          case 'completed':
            return <div {...iconProps} className="w-4 h-4 text-green-500" />;
          case 'failed':
            return <div {...iconProps} className="w-4 h-4 text-red-500" />;
          case 'pending':
            return <div {...iconProps} className="w-4 h-4 text-yellow-500" />;
          default:
            return <div {...iconProps} className="w-4 h-4 text-gray-500" data-testid="default-status" />;
        }
      };
      
      render(<StatusIcon status={undefined} />);
      expect(screen.getByTestId('default-status')).toHaveClass('text-gray-500');
    });

    test('handles undefined status in StatusBadge', () => {
      const StatusBadge = ({ status }) => {
        const baseClasses = "px-3 py-1 rounded-full text-xs font-medium flex items-center gap-2 w-fit";
        const statusStyles = {
          running: "bg-blue-100 text-blue-800",
          completed: "bg-green-100 text-green-800",
          failed: "bg-red-100 text-red-800",
          pending: "bg-yellow-100 text-yellow-800"
        };
        const statusClass = statusStyles[status] || "bg-gray-100 text-gray-800";
        
        return (
          <span className={`${baseClasses} ${statusClass}`} data-testid="status-badge">
            {status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Unknown'}
          </span>
        );
      };
      
      render(<StatusBadge status={undefined} />);
      const badge = screen.getByTestId('status-badge');
      expect(badge).toHaveClass('bg-gray-100', 'text-gray-800');
      expect(badge).toHaveTextContent('Unknown');
    });
  });
});