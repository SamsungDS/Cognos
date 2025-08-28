import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import Events from '../pages/Events';
import { useEvents } from '../contexts/EventsContext';

// Mock the EventsContext
jest.mock('../contexts/EventsContext', () => ({
    useEvents: jest.fn()
}));

// Mock CSS import
jest.mock('../pages/events.css', () => ({}));

// Mock Lucide React icons
jest.mock('lucide-react', () => ({
    AlertTriangle: ({ size, className }) => <div data-testid="alert-triangle-icon" className={className} style={{ width: size, height: size }} />,
    CheckCircle: ({ size, className }) => <div data-testid="check-circle-icon" className={className} style={{ width: size, height: size }} />,
    Info: ({ size, className }) => <div data-testid="info-icon" className={className} style={{ width: size, height: size }} />,
    X: ({ size }) => <div data-testid="x-icon" style={{ width: size, height: size }} />,
    Bell: ({ size, className }) => <div data-testid="bell-icon" className={className} style={{ width: size, height: size }} />,
    Search: ({ size, className }) => <div data-testid="search-icon" className={className} style={{ width: size, height: size }} />,
    ShieldAlert: ({ size, className }) => <div data-testid="shield-alert-icon" className={className} style={{ width: size, height: size }} />,
    Clock: ({ size, className }) => <div data-testid="clock-icon" className={className} style={{ width: size, height: size }} />,
    Trash2: ({ size, className }) => <div data-testid="trash-icon" className={className} style={{ width: size, height: size }} />,
    RefreshCw: ({ size, className }) => <div data-testid="refresh-icon" className={className} style={{ width: size, height: size }} />
}));

const mockEvents = [
    {
        id: '1',
        event_msg: 'Critical system failure',
        event_name: 'System Failure',
        source: 'Database',
        source_type: 'MySQL',
        node_name: 'db-server-01',
        severity: 'critical',
        timestamp: '2025-01-15 10:30:00',
        category: 'System'
    },
    {
        id: '2',
        event_msg: 'High CPU usage detected',
        event_name: 'CPU Warning',
        source: 'Monitor',
        source_type: 'System Monitor',
        node_name: 'web-server-01',
        severity: 'warning',
        timestamp: '2025-01-15 11:45:00',
        category: 'Performance'
    },
    {
        id: '3',
        event_msg: 'System backup completed successfully',
        event_name: 'Backup Complete',
        source: 'Backup Service',
        source_type: 'Automated',
        node_name: 'backup-server-01',
        severity: 'info',
        timestamp: '2025-01-15 12:00:00',
        category: 'Maintenance'
    }
];

const mockSetEvents = jest.fn();
const mockUseEvents = useEvents;

describe('Events Component', () => {
    beforeEach(() => {
        mockSetEvents.mockClear();
        mockUseEvents.mockReturnValue({
            events: mockEvents,
            setEvents: mockSetEvents
        });
    });

    afterEach(() => {
        jest.clearAllMocks();
    });

    describe('Component Rendering', () => {
        test('renders the Events component with header', () => {
            render(<Events />);

            expect(screen.getByText('System Events')).toBeInTheDocument();
            expect(screen.getByText('Monitor and manage system events')).toBeInTheDocument();
            expect(screen.getByTestId('bell-icon')).toBeInTheDocument();
        });

        test('renders refresh button', () => {
            render(<Events />);

            const refreshButton = screen.getByRole('button', { name: /refresh/i });
            expect(refreshButton).toBeInTheDocument();
            expect(refreshButton).toBeDisabled();
        });

        test('renders filter dropdown with correct options', () => {
            render(<Events />);

            const filterSelect = screen.getByDisplayValue(/all events/i);
            expect(filterSelect).toBeInTheDocument();

            // Check if options exist
            expect(screen.getByText(/all events \(3\)/i)).toBeInTheDocument();
            expect(screen.getByText(/critical \(1\)/i)).toBeInTheDocument();
            expect(screen.getByText(/warnings \(1\)/i)).toBeInTheDocument();
            expect(screen.getByText(/info \(1\)/i)).toBeInTheDocument();
        });
    });
describe('Event Selection', () => {
        test('selects and deselects individual events', async () => {
            render(<Events />);

            const checkboxes = screen.getAllByRole('checkbox');

            // Select first event
            await userEvent.click(checkboxes[0]);
            expect(checkboxes[0]).toBeChecked();

            // Should show "Clear Selected" button
            expect(screen.getByText(/clear selected \(1\)/i)).toBeInTheDocument();

            // Deselect
            await userEvent.click(checkboxes[0]);
            expect(checkboxes[0]).not.toBeChecked();
        });
    });
});
describe('Empty States', () => {
    test('shows "All Clear" when no events exist', () => {
        mockUseEvents.mockReturnValue({
            events: [],
            setEvents: mockSetEvents
        });

        render(<Events />);

        expect(screen.getByText('All Clear!')).toBeInTheDocument();
        expect(screen.getByText('There are no active events at this time. Your system is running smoothly.')).toBeInTheDocument();
        expect(screen.getByTestId('check-circle-icon')).toBeInTheDocument();
    });

});
describe('Button States', () => {
    test('clear all button is disabled when no events match filter', () => {
        mockUseEvents.mockReturnValue({
            events: [],
            setEvents: mockSetEvents
        });

        render(<Events />);

        const clearButton = screen.getByText(/clear all events/i);
        expect(clearButton).toBeDisabled();
    });

});
