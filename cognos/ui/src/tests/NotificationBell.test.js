import { render, screen } from '@testing-library/react';
import NotificationBell from '../components/NotificationBell';
import { useEvents } from '../contexts/EventsContext';

// Mock the EventsContext
jest.mock('../contexts/EventsContext', () => ({
    useEvents: jest.fn(),
}));

// Mock lucide-react Bell icon
jest.mock('lucide-react', () => ({
    Bell: ({ className, ...props }) => (
        <svg className={className} data-testid="bell-icon" {...props}>
            <title>Bell</title>
        </svg>
    ),
}));


describe('NotificationBell Component', () => {
    const mockUseEvents = useEvents;

    beforeEach(() => {
        jest.clearAllMocks();
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.runOnlyPendingTimers();
        jest.useRealTimers();
    });

    describe('Rendering', () => {
        test('should render the bell icon', () => {
            mockUseEvents.mockReturnValue({ notificationCount: 0 });

            render(<NotificationBell />);

            expect(screen.getByTestId('bell-icon')).toBeInTheDocument();
        });

        test('should render with proper accessibility attributes', () => {
            mockUseEvents.mockReturnValue({ notificationCount: 5 });

            render(<NotificationBell />);

            const bellContainer = screen.getByRole('button');
            expect(bellContainer).toHaveAttribute('tabIndex', '0');
        });

        test('should not have disabled styling when notification count is greater than 0', () => {
            mockUseEvents.mockReturnValue({ notificationCount: 3 });

            render(<NotificationBell />);

            const bellContainer = screen.getByRole('button');
            expect(bellContainer).not.toHaveClass('disabled');
        });
    });
});
