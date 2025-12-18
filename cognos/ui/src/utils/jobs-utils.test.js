import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import {
    LoadingSpinner,
    ErrorMessage,
    FormField,
    StatusBadge,
    JobRow,
    EmptyState,
    jobApiService,
    validateForm,
    columnHeader
} from './jobs-utils'; // Update with actual file path

// Mock fetch for API tests
global.fetch = jest.fn();

describe('columnHeader', () => {
    it('should have correct column headers', () => {
        expect(columnHeader).toEqual([
            "App Name",
            "App PID",
            "Server node",
            "Target Throughput(ops / s)",
            "Target Read P99 Latency(us)",
            "Target Write P99 Latency(us)",
            "Status",
            "Message"
        ]);
    });
});

describe('LoadingSpinner', () => {
    it('should render loading spinner', () => {
        const { container } = render(<LoadingSpinner />);
        expect(container.querySelector('.custom-spinner')).toBeInTheDocument();
    });
});

describe('ErrorMessage', () => {
    it('should render error message when error exists and show is true', () => {
        render(<ErrorMessage error="Test error" show={true} />);
        expect(screen.getByText('Test error')).toBeInTheDocument();
    });

    it('should not render when show is false', () => {
        const { container } = render(<ErrorMessage error="Test error" show={false} />);
        expect(container.firstChild).toBeNull();
    });

    it('should not render when error is null', () => {
        const { container } = render(<ErrorMessage error={null} show={true} />);
        expect(container.firstChild).toBeNull();
    });

    it('should not render when error is undefined', () => {
        const { container } = render(<ErrorMessage error={undefined} />);
        expect(container.firstChild).toBeNull();
    });
});

describe('FormField', () => {
    const mockOnChange = jest.fn();

    beforeEach(() => {
        mockOnChange.mockClear();
    });

    it('should render form field with label', () => {
        render(
            <FormField
                label="Test Label"
                value=""
                onChange={mockOnChange}
            />
        );
        expect(screen.getByText('Test Label')).toBeInTheDocument();
    });

    it('should show required asterisk when required is true', () => {
        render(
            <FormField
                label="Required Field"
                value=""
                onChange={mockOnChange}
                required={true}
            />
        );
        expect(screen.getByText('*')).toBeInTheDocument();
    });

    it('should call onChange when input value changes', () => {
        render(
            <FormField
                label="Test Field"
                value=""
                onChange={mockOnChange}
                placeholder="Enter value"
            />
        );
        const input = screen.getByPlaceholderText('Enter value');
        fireEvent.change(input, { target: { value: 'new value' } });
        expect(mockOnChange).toHaveBeenCalledWith('new value');
    });

    it('should display error message when error exists', () => {
        render(
            <FormField
                label="Test Field"
                value=""
                onChange={mockOnChange}
                error="This field is required"
            />
        );
        expect(screen.getByText('This field is required')).toBeInTheDocument();
    });

    it('should not display error when disabled', () => {
        const { container } = render(
            <FormField
                label="Test Field"
                value=""
                onChange={mockOnChange}
                error="This field is required"
                disabled={true}
            />
        );
        expect(container.querySelector('.custom-error-text')).not.toBeInTheDocument();
    });

    it('should display help text when provided', () => {
        render(
            <FormField
                label="Test Field"
                value=""
                onChange={mockOnChange}
                helpText="This is help text"
            />
        );
        expect(screen.getByText('This is help text')).toBeInTheDocument();
    });

    it('should render children instead of input when provided', () => {
        render(
            <FormField
                label="Custom Field"
                value=""
                onChange={mockOnChange}
            >
                <div data-testid="custom-child">Custom Input</div>
            </FormField>
        );
        expect(screen.getByTestId('custom-child')).toBeInTheDocument();
    });

    it('should disable input when disabled prop is true', () => {
        render(
            <FormField
                label="Disabled Field"
                value="test"
                onChange={mockOnChange}
                disabled={true}
                placeholder="Disabled input"
            />
        );
        const input = screen.getByPlaceholderText('Disabled input');
        expect(input).toBeDisabled();
    });
});

describe('StatusBadge', () => {
    it('should render badge with "good" status', () => {
        render(<StatusBadge status="good" />);
        expect(screen.getByText('good')).toBeInTheDocument();
    });

    it('should render badge with "degraded" status', () => {
        render(<StatusBadge status="degraded" />);
        expect(screen.getByText('degraded')).toBeInTheDocument();
    });

    it('should render badge with "device_degraded" status', () => {
        render(<StatusBadge status="device_degraded" />);
        expect(screen.getByText('device_degraded')).toBeInTheDocument();
    });

    it('should render badge with "failed" status', () => {
        render(<StatusBadge status="failed" />);
        expect(screen.getByText('failed')).toBeInTheDocument();
    });

    it('should apply default class for unknown status', () => {
        render(<StatusBadge status="unknown" />);
        expect(screen.getByText('unknown')).toBeInTheDocument();
    });
});

describe('JobRow', () => {
    const mockJob = {
        app_name: 'Test App',
        app_pid: '12345',
        server_name: 'Server1',
        throughput_ops_per_sec: '1000',
        targetread_p99_latency: '50',
        targetwrite_p99_latency: '100',
        status: 'good',
        data_moved: '75',
        message: 'test_message_here'
    };

    it('should render all job details', () => {
        render(
            <table>
                <tbody>
                    <JobRow job={mockJob} />
                </tbody>
            </table>
        );

        expect(screen.getByText('Test App')).toBeInTheDocument();
        expect(screen.getByText('12345')).toBeInTheDocument();
        expect(screen.getByText('Server1')).toBeInTheDocument();
        expect(screen.getByText('1000')).toBeInTheDocument();
        expect(screen.getByText('50')).toBeInTheDocument();
        expect(screen.getByText('100')).toBeInTheDocument();
        expect(screen.getByText('good')).toBeInTheDocument();
    });

    it('should replace underscores in message with spaces', () => {
        render(
            <table>
                <tbody>
                    <JobRow job={mockJob} />
                </tbody>
            </table>
        );

        expect(screen.getByText('test message here')).toBeInTheDocument();
    });

    it('should display data_moved in title attribute', () => {
        const { container } = render(
            <table>
                <tbody>
                    <JobRow job={mockJob} />
                </tbody>
            </table>
        );

        const statusCell = container.querySelector('td[title="data moved: 75%"]');
        expect(statusCell).toBeInTheDocument();
    });
});

describe('EmptyState', () => {
    it('should render empty state message', () => {
        render(<EmptyState />);
        expect(screen.getByText('No apps found')).toBeInTheDocument();
        expect(screen.getByText('No apps currently being monitored, please register application')).toBeInTheDocument();
    });
});

describe('jobApiService', () => {
    beforeEach(() => {
        fetch.mockClear();
    });

    describe('getAllJobs', () => {
        it('should fetch jobs successfully', async () => {
            const mockData = [
                { app_name: 'App1', status: 'good' },
                { app_name: 'App2', status: 'degraded' }
            ];

            fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => mockData,
            });

            const result = await jobApiService.getAllJobs();
            expect(result).toEqual(mockData);
            expect(fetch).toHaveBeenCalledWith(
                expect.stringContaining('/application_status'),
                expect.objectContaining({
                    method: 'GET',
                    mode: 'cors',
                    headers: expect.objectContaining({
                        'Content-Type': 'application/json',
                    }),
                })
            );
        });

        it('should throw error when response is not ok', async () => {
            fetch.mockResolvedValueOnce({
                ok: false,
                status: 404,
            });

            await expect(jobApiService.getAllJobs()).rejects.toThrow('HTTP error! status: 404');
        });

        it('should throw error when fetch fails', async () => {
            fetch.mockRejectedValueOnce(new Error('Network error'));

            await expect(jobApiService.getAllJobs()).rejects.toThrow('Network error');
        });
    });
});

describe('validateForm', () => {
    it('should return no errors for valid form data', () => {
        const formData = {
            app_pid: '12345',
            app_name: 'Test App',
            avg_latency_ns: '100',
            throughput_ops_per_sec: '1000',
            targetread_p99_latency: '50',
            targetwrite_p99_latency: '100'
        };

        const errors = validateForm(formData);
        expect(Object.keys(errors).length).toBe(0);
    });

    it('should return error when app_pid is missing', () => {
        const formData = {
            app_name: 'Test App',
            avg_latency_ns: '100',
            throughput_ops_per_sec: '1000',
            targetread_p99_latency: '50',
            targetwrite_p99_latency: '100'
        };

        const errors = validateForm(formData);
        expect(errors.app_pid).toBe('Application PID is required');
    });

    it('should return error when app_name is missing', () => {
        const formData = {
            app_pid: '12345',
            avg_latency_ns: '100',
            throughput_ops_per_sec: '1000',
            targetread_p99_latency: '50',
            targetwrite_p99_latency: '100'
        };

        const errors = validateForm(formData);
        expect(errors.app_name).toBe('Application Name is required');
    });

    it('should return error when avg_latency_ns is missing', () => {
        const formData = {
            app_pid: '12345',
            app_name: 'Test App',
            throughput_ops_per_sec: '1000',
            targetread_p99_latency: '50',
            targetwrite_p99_latency: '100'
        };

        const errors = validateForm(formData);
        expect(errors.avg_latency_ns).toBe('Average Latency is required');
    });

    it('should return error when throughput_ops_per_sec is missing', () => {
        const formData = {
            app_pid: '12345',
            app_name: 'Test App',
            avg_latency_ns: '100',
            targetread_p99_latency: '50',
            targetwrite_p99_latency: '100'
        };

        const errors = validateForm(formData);
        expect(errors.throughput_ops_per_sec).toBe('Throughput is required');
    });

    it('should return error when targetread_p99_latency is missing', () => {
        const formData = {
            app_pid: '12345',
            app_name: 'Test App',
            avg_latency_ns: '100',
            throughput_ops_per_sec: '1000',
            targetwrite_p99_latency: '100'
        };

        const errors = validateForm(formData);
        expect(errors.targetread_p99_latency).toBe('target read p99 latency is required');
    });

    it('should return error when targetwrite_p99_latency is missing', () => {
        const formData = {
            app_pid: '12345',
            app_name: 'Test App',
            avg_latency_ns: '100',
            throughput_ops_per_sec: '1000',
            targetread_p99_latency: '50'
        };

        const errors = validateForm(formData);
        expect(errors.targetwrite_p99_latency).toBe('target write p99 latency is required');
    });

    it('should return multiple errors when multiple fields are missing', () => {
        const formData = {};

        const errors = validateForm(formData);
        expect(Object.keys(errors).length).toBeGreaterThan(0);
        expect(errors.app_pid).toBeDefined();
        expect(errors.app_name).toBeDefined();
        expect(errors.avg_latency_ns).toBeDefined();
    });
});