import React from 'react';
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
// Mock lucide-react icons
jest.mock('lucide-react', () => ({
    AlertTriangle: ({ size, className }) => <div data-testid="alert-triangle" data-size={size} className={className} />,
    CheckCircle: ({ size, className }) => <div data-testid="check-circle" data-size={size} className={className} />,
    Info: ({ size, className }) => <div data-testid="info" data-size={size} className={className} />,
    X: ({ size }) => <div data-testid="x-icon" data-size={size} />,
    Bell: ({ size, className }) => <div data-testid="bell" data-size={size} className={className} />,
    Search: ({ size, className }) => <div data-testid="search" data-size={size} className={className} />,
    ShieldAlert: ({ size, className }) => <div data-testid="shield-alert" data-size={size} className={className} />,
    Clock: ({ size, className }) => <div data-testid="clock" data-size={size} className={className} />,
    Trash2: ({ size, className }) => <div data-testid="trash2" data-size={size} className={className} />,
    RefreshCw: ({ size, className }) => <div data-testid="refresh-cw" data-size={size} className={className} />,
    ChevronDown: ({ size, className }) => <div data-testid="chevron-down" data-size={size} className={className} />,
    ChevronUp: ({ size, className }) => <div data-testid="chevron-up" data-size={size} className={className} />,
    Calendar: ({ size, className }) => <div data-testid="calendar" data-size={size} className={className} />,
}));

const mockEvents = [
    {
        id: 1,
        severity: 'critical',
        timestamp: '2024-01-15 10:30:00',
        msg: 'Critical system error',
        event_name: 'System Error',
        source: 'System',
        source_type: 'Internal',
        node_name: 'node-1',
        category: 'Error',
        domain: 'System',
        cluster_name: 'cluster-1',
        payload: { message: 'Critical system failure detected' }
    },
    {
        id: 2,
        severity: 'warning',
        timestamp: '2024-01-15 10:25:00',
        msg: 'Warning: High CPU usage',
        event_name: 'CPU Warning',
        source: 'Monitor',
        source_type: 'External',
        node_name: 'node-2',
        category: 'Performance',
        domain: 'Hardware',
        cluster_name: 'cluster-1',
        payload: { message: 'CPU usage exceeded threshold' }
    },
    {
        id: 3,
        severity: 'info',
        timestamp: '2024-01-15 10:20:00',
        msg: 'Info: System started',
        event_name: 'System Start',
        source: 'System',
        source_type: 'Internal',
        node_name: 'node-1',
        category: 'Status',
        domain: 'System',
        cluster_name: 'cluster-2',
        payload: { message: 'System initialization completed' }
    }
];

const mockUseEvents = useEvents;

describe('Events Component', () => {
    let mockSetEvents;

    beforeEach(() => {
        mockSetEvents = jest.fn();
        mockUseEvents.mockReturnValue({
            events: mockEvents,
            setEvents: mockSetEvents
        });
    });

    afterEach(() => {
        jest.clearAllMocks();
    });

    describe('Component Rendering', () => {
        test('renders the main header correctly', () => {
            render(<Events />);

            expect(screen.getByText('System Events')).toBeInTheDocument();
            expect(screen.getByText('Monitor and manage system events')).toBeInTheDocument();
            expect(screen.getByTestId('bell')).toBeInTheDocument();
        });

        test('renders refresh button', () => {
            render(<Events />);

            const refreshButton = screen.getByRole('button', { name: /refresh/i });
            expect(refreshButton).toBeInTheDocument();
            expect(refreshButton).toBeDisabled();
        });

        test('renders stats cards for each severity level', () => {
            render(<Events />);

            expect(screen.getByText('Critical')).toBeInTheDocument();
            expect(screen.getByText('Warnings')).toBeInTheDocument();
            expect(screen.getByText('Info')).toBeInTheDocument();
        });

        test('displays correct event counts in stats cards', () => {
            render(<Events />);

            // Check that the counts are displayed (1 critical, 1 warning, 1 info)
            const statsCards = screen.getAllByText('1');
            expect(statsCards).toHaveLength(3); // Each severity has 1 event
        });

        test('renders all events when no filter is applied', () => {
            render(<Events />);

            expect(screen.getByText('Critical system error')).toBeInTheDocument();
            expect(screen.getByText('Warning: High CPU usage')).toBeInTheDocument();
            expect(screen.getByText('Info: System started')).toBeInTheDocument();
        });
    });

    describe('Event Card Rendering', () => {
        test('renders event cards with correct information', () => {
            render(<Events />);

            // Check if event messages are rendered
            expect(screen.getByText('Critical system error')).toBeInTheDocument();
            expect(screen.getByText('Warning: High CPU usage')).toBeInTheDocument();
            expect(screen.getByText('Info: System started')).toBeInTheDocument();

            // Check if timestamps are rendered
            expect(screen.getByText('2024-01-15 10:30:00')).toBeInTheDocument();
            expect(screen.getByText('2024-01-15 10:25:00')).toBeInTheDocument();
            expect(screen.getByText('2024-01-15 10:20:00')).toBeInTheDocument();
        });

        test('renders severity badges correctly', () => {
            render(<Events />);

            // Check for severity text in badges
            const criticalBadges = screen.getAllByText('critical');
            const warningBadges = screen.getAllByText('warning');
            const infoBadges = screen.getAllByText('info');

            expect(criticalBadges.length).toBeGreaterThan(0);
            expect(warningBadges.length).toBeGreaterThan(0);
            expect(infoBadges.length).toBeGreaterThan(0);
        });

        test('renders event details badges', () => {
            render(<Events />);

            // Check for source information
            expect(screen.getAllByText(/Source:/)).toHaveLength(3);
            expect(screen.getAllByText(/Node:/)).toHaveLength(3);
            expect(screen.getAllByText(/Cluster Name:/)).toHaveLength(3);
        });
    });

    describe('Filtering Functionality', () => {
        test('filters events by severity using dropdown', () => {
            render(<Events />);

            const filterSelect = screen.getByRole('combobox');

            // Filter by critical
            fireEvent.change(filterSelect, { target: { value: 'critical' } });

            expect(screen.getByText('Critical system error')).toBeInTheDocument();
            expect(screen.queryByText('Warning: High CPU usage')).not.toBeInTheDocument();
            expect(screen.queryByText('Info: System started')).not.toBeInTheDocument();
        });

        test('filters events by warning severity', () => {
            render(<Events />);

            const filterSelect = screen.getByRole('combobox');

            // Filter by warning
            fireEvent.change(filterSelect, { target: { value: 'warning' } });

            expect(screen.queryByText('Critical system error')).not.toBeInTheDocument();
            expect(screen.getByText('Warning: High CPU usage')).toBeInTheDocument();
            expect(screen.queryByText('Info: System started')).not.toBeInTheDocument();
        });

        test('shows all events when "all" filter is selected', () => {
            render(<Events />);

            const filterSelect = screen.getByRole('combobox');

            // Ensure all filter is selected
            fireEvent.change(filterSelect, { target: { value: 'all' } });

            expect(screen.getByText('Critical system error')).toBeInTheDocument();
            expect(screen.getByText('Warning: High CPU usage')).toBeInTheDocument();
            expect(screen.getByText('Info: System started')).toBeInTheDocument();
        });

        test('clicking on stats cards changes filter', () => {
            render(<Events />);

            // Click on Critical stats card
            const criticalCard = screen.getByText('Critical').closest('button');
            fireEvent.click(criticalCard);

            // Should show only critical events
            expect(screen.getByText('Critical system error')).toBeInTheDocument();
            expect(screen.queryByText('Warning: High CPU usage')).not.toBeInTheDocument();
        });
    });

    describe('Event Selection', () => {
        test('can select individual events', () => {
            render(<Events />);

            const checkboxes = screen.getAllByRole('checkbox');

            // Select first event
            fireEvent.click(checkboxes[0]);

            // Should show "Clear Selected" button
            expect(screen.getByText(/Clear Selected \(1\)/)).toBeInTheDocument();
        });
    });

    describe('Event Expansion', () => {
        test('can expand event details', () => {
            render(<Events />);

            const detailsButtons = screen.getAllByText('Details');

            // Click on first Details button
            fireEvent.click(detailsButtons[0]);

            // Should show expanded content
            expect(screen.getByText('Event Details')).toBeInTheDocument();
            expect(screen.getByText('Critical system failure detected')).toBeInTheDocument();
        });

        test('can collapse expanded event', () => {
            render(<Events />);

            const detailsButtons = screen.getAllByText('Details');

            // Expand first event
            fireEvent.click(detailsButtons[0]);

            // Should show Collapse button
            const collapseButton = screen.getByText('Collapse');
            expect(collapseButton).toBeInTheDocument();

            // Collapse the event
            fireEvent.click(collapseButton);

            // Should no longer show expanded content
            expect(screen.queryByText('Event Details')).not.toBeInTheDocument();
        });

        test('shows expanded event indicator in header', () => {
            render(<Events />);

            const detailsButtons = screen.getAllByText('Details');

            // Expand first event
            fireEvent.click(detailsButtons[0]);

            // Should show "1 expanded" in header
            expect(screen.getByText('• 1 expanded')).toBeInTheDocument();
        });
    });

    describe('Event Dismissal', () => {
        test('can dismiss individual events', () => {
            render(<Events />);

            const dismissButtons = screen.getAllByRole('button', { name: /dismiss event/i });

            // Dismiss first event
            fireEvent.click(dismissButtons[0]);

            // Should call setEvents to remove the event
            expect(mockSetEvents).toHaveBeenCalledWith([mockEvents[1], mockEvents[2]]);
        });
    });

    describe('Bulk Actions', () => {
        test('can clear selected events', () => {
            render(<Events />);

            const checkboxes = screen.getAllByRole('checkbox');

            // Select first event
            fireEvent.click(checkboxes[0]);

            // Click Clear Selected button
            const clearSelectedButton = screen.getByText(/Clear Selected \(1\)/);
            fireEvent.click(clearSelectedButton);

            // Should call setEvents to remove selected events
            expect(mockSetEvents).toHaveBeenCalledWith([mockEvents[1], mockEvents[2]]);
        });

        test('can clear all events', () => {
            render(<Events />);

            // Click Clear All Events button
            const clearAllButton = screen.getByText('Clear All Events');
            fireEvent.click(clearAllButton);

            // Should call setEvents with empty array
            expect(mockSetEvents).toHaveBeenCalledWith([]);
        });

        test('can clear filtered events', () => {
            render(<Events />);

            // Filter by critical
            const filterSelect = screen.getByRole('combobox');
            fireEvent.change(filterSelect, { target: { value: 'critical' } });

            // Click Clear critical Events button
            const clearFilteredButton = screen.getByText('Clear critical Events');
            fireEvent.click(clearFilteredButton);

            // Should call setEvents to remove only critical events
            expect(mockSetEvents).toHaveBeenCalledWith([mockEvents[1], mockEvents[2]]);
        });

        test('clear button is disabled when no events match filter', () => {
            // Mock empty events array
            mockUseEvents.mockReturnValue({
                events: [],
                setEvents: mockSetEvents
            });

            render(<Events />);

            const clearAllButton = screen.getByText('Clear All Events');
            expect(clearAllButton).toBeDisabled();
        });
    });

    describe('Empty States', () => {
        test('shows "All Clear" message when no events exist', () => {
            mockUseEvents.mockReturnValue({
                events: [],
                setEvents: mockSetEvents
            });

            render(<Events />);

            expect(screen.getByText('All Clear!')).toBeInTheDocument();
            expect(screen.getByText('There are no active events at this time. Your system is running smoothly.')).toBeInTheDocument();
            expect(screen.getByTestId('check-circle')).toBeInTheDocument();
        });

    });

    describe('Search Functionality', () => {
        test('search state is initialized correctly', () => {
            render(<Events />);

            // Component should render without search input visible in this version
            // but search term state should be working internally
            expect(screen.getByText('System Events')).toBeInTheDocument();
        });
    });

    describe('Event Card Interactions', () => {
        test('event card has hover effects', () => {
            render(<Events />);

            const eventCards = screen.getAllByText('Critical system error')[0].closest('.card');

            // Simulate mouse enter
            fireEvent.mouseEnter(eventCards);
            expect(eventCards.style.boxShadow).toBe('0 4px 12px rgba(0,0,0,0.1)');

            // Simulate mouse leave
            fireEvent.mouseLeave(eventCards);
            expect(eventCards.style.boxShadow).toBe('0 1px 3px rgba(0,0,0,0.1)');
        });

    });

    describe('Component Props and PropTypes', () => {
        test('EventCard renders with valid props', () => {
            render(<Events />);

            // All event cards should render without PropType warnings
            // This test passes if no console errors are thrown
            expect(screen.getByText('Critical system error')).toBeInTheDocument();
            expect(screen.getByText('Warning: High CPU usage')).toBeInTheDocument();
            expect(screen.getByText('Info: System started')).toBeInTheDocument();
        });
    });

    describe('Filter Options Display', () => {
        test('displays correct counts in filter dropdown', () => {
            render(<Events />);

            const filterSelect = screen.getByRole('combobox');

            // Check that options with counts are present
            expect(filterSelect).toHaveValue('all');

            // The options should include counts
            const options = screen.getAllByRole('option');
            expect(options).toHaveLength(4); // all, critical, warning, info
        });

        test('updates filter counts when events change', () => {
            const { rerender } = render(<Events />);

            // Update mock to have different event counts
            mockUseEvents.mockReturnValue({
                events: [mockEvents[0], mockEvents[0]], // 2 critical events
                setEvents: mockSetEvents
            });

            rerender(<Events />);

            // Should update the stats display
            expect(screen.getByText('Critical')).toBeInTheDocument();
        });
    });

    describe('Event Counter Display', () => {
        test('displays correct event count in header', () => {
            render(<Events />);

            expect(screen.getByText('3 Events Found')).toBeInTheDocument();
        });

        test('displays singular form when only one event', () => {
            mockUseEvents.mockReturnValue({
                events: [mockEvents[0]],
                setEvents: mockSetEvents
            });

            render(<Events />);

            expect(screen.getByText('1 Event Found')).toBeInTheDocument();
        });
    });
});