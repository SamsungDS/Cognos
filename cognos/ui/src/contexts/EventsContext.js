import React, { useContext, useState, useEffect, createContext } from 'react';
import * as constants from '../constant';


// Mock data - moved to top for better organization
const mockEventData = [
    {
        id: 1,
        severity: 'critical',
        node_name: 'NODE-001',
        node_id: 'NODE-001',
        category: 'Security',
        source: 'Node',
        source_type: 'device',
        timestamp: '2 min ago',
        event_name: "node down",
        event_msg: 'Node is showing unhealthy status'
    },
    {
        id: 2,
        severity: 'warning',
        node_name: 'NODE-002',
        node_id: 'NODE-002',
        category: 'Security',
        source: 'Node-02',
        source_type: 'device',
        timestamp: '5 min ago',
        event_name: "node-02 down",
        event_msg: 'Node-02 is showing unhealthy status'
    },
    {
        id: 3,
        severity: 'info',
        node_name: 'NODE-003',
        node_id: 'NODE-003',
        category: 'Performance',
        source: 'Node-03',
        source_type: 'device',
        timestamp: '10 min ago',
        event_name: "performance degraded",
        event_msg: 'Node-03 performance is below threshold'
    },
    {
        id: 4,
        severity: 'info',
        node_name: 'NODE-004',
        node_id: 'NODE-004',
        category: 'Performance',
        source: 'Node-04',
        source_type: 'device',
        timestamp: '15 min ago',
        event_name: "performance degraded",
        event_msg: 'Node-04 performance is below threshold'
    },
    {
        id: 5,
        severity: 'warning',
        node_name: 'NODE-005',
        node_id: 'NODE-005',
        category: 'System',
        source: 'Node-05',
        source_type: 'device',
        timestamp: '20 min ago',
        event_name: "memory usage high",
        event_msg: 'Node-05 memory usage is above 85%'
    }
];

// Create Events Context with default values
export const EventsContext = createContext({
    events: [],
    setEvents: () => { },
    isLoading: false,
    error: null,
    notificationCount: 0,
    hasEvents: false,
    eventCount: 0,
    criticalEvents: [],
    warningEvents: [],
    infoEvents: [],
    addEvent: () => { },
    removeEvent: () => { },
    clearEvents: () => { },
    refreshEvents: () => { }
});

// Events Provider Component
export const EventsProvider = ({ children }) => {
    // Main state - using 'events' terminology consistently
    const [events, setEvents] = useState(mockEventData);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const apiEndpoint = constants.Configs.api_endpoint;

    // Fetch event data function
    // istanbul ignore next
    const fetchEventData = async () => {
        setIsLoading(true);
        setError(null);

        try {
            const response = await fetch(`${apiEndpoint}/events`);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            // Handle different API response formats
            const eventsData = Array.isArray(data) ? data : data.events || data.alerts || [];
            console.log("Events Data: ", eventsData);
            setEvents(eventsData);

        } catch (error) {
            console.error('Error fetching event data:', error);
            setError(error.message);
            // Keep existing events on error instead of setting to null
        } finally {
            setIsLoading(false);
        }
    };

    // Add new event function
    // istanbul ignore next
    const addEvent = (newEvent) => {
        const event = {
            ...newEvent,
            id: newEvent.id || Date.now(),
            timestamp: newEvent.timestamp || 'now'
        };
        setEvents(prev => [event, ...prev]);
    };

    // Remove event function
    // istanbul ignore next
    const removeEvent = (eventId) => {
        setEvents(prev => prev.filter(event => event.id !== eventId));
    };

    // Clear all events
    const clearEvents = () => {
        setEvents([]);
    };

    // Refresh events function
    const refreshEvents = () => {
        fetchEventData();
    };

    // Set up polling effect
    useEffect(() => {
        // Uncomment the line below if you want to fetch from API on mount
        fetchEventData();

        // Poll for updates every 30 seconds (commented out for development)
        const interval = setInterval(fetchEventData, 5000);
        return () => clearInterval(interval);
    }, []);

    // Helper functions
    const getTotalCount = () => events?.length || 0;
    const getEventsBySeverity = (severity) => events?.filter(event => event.severity === severity) || [];

    // Context value with computed properties
    const contextValue = {
        // Main state
        events,
        setEvents,
        isLoading,
        error,

        // Helper functions
        addEvent,
        removeEvent,
        clearEvents,
        refreshEvents,

        // Computed values
        notificationCount: getTotalCount(),
        hasEvents: events && events.length > 0,
        eventCount: events?.length || 0,
        criticalEvents: getEventsBySeverity('critical'),
        warningEvents: getEventsBySeverity('warning'),
        infoEvents: getEventsBySeverity('info')
    };

    return (
        <EventsContext.Provider value={contextValue}>
            {children}
        </EventsContext.Provider>
    );
};

// Custom hook to use Events Context
// istanbul ignore next
export const useEvents = () => {
    const context = useContext(EventsContext);
    if (!context) {
        throw new Error('useEvents must be used within an EventsProvider');
    }
    return context;
};

// Export mock data for reuse
export { mockEventData };