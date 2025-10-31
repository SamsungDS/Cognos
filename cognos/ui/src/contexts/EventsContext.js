import React, { useContext, useState, useEffect, createContext } from 'react';
import * as constants from '../constant';

// Mock data - moved to top for better organization
const mockEventData = [
    {
        timestamp: "12:40:05",
        msg: "Node is showing unhealthy status",
        payload: { message: "axy" },
        cluster_name: "node",
        node_name: "node-1",
        severity: 'critical',
        domain: 'NODE-001',
        category: 'Security',
        source: 'Node',
        source_type: 'device'
    }
];

// Utility function to ensure all events have unique IDs
// istanbul ignore next
const ensureEventIds = (eventsArray) => {
    if (!Array.isArray(eventsArray)) return [];

    return eventsArray.map((event, index) => ({
        ...event,
        // eslint-disable-next-line no-restricted-syntax
        id: event.id || `event-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 11)}`
    }));
};

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
    // Main state - initialize with IDs
    // eslint-disable-next-line react/hook-use-state
    const [events, setEventsInternal] = useState(() => ensureEventIds(mockEventData));
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const apiEndpoint = constants.Configs.api_endpoint;

    // Wrapper for setEvents that ensures IDs
    // istanbul ignore next
    const setEvents = (eventsOrUpdater) => {
        if (typeof eventsOrUpdater === 'function') {
            setEventsInternal(prev => {
                const newEvents = eventsOrUpdater(prev);
                return ensureEventIds(newEvents);
            });
        } else {
            setEventsInternal(ensureEventIds(eventsOrUpdater));
        }
    };

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
            console.log("Events Data (raw):", eventsData);

            // Ensure all events have IDs before setting
            const eventsWithIds = ensureEventIds(eventsData);
            console.log("Events Data (with IDs):", eventsWithIds);

            setEventsInternal(eventsWithIds);

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
            // eslint-disable-next-line no-restricted-syntax
            id: newEvent.id || `event-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
            timestamp: newEvent.timestamp || new Date().toLocaleTimeString()
        };
        setEventsInternal(prev => [event, ...prev]);
    };

    // Remove event function
    // istanbul ignore next
    const removeEvent = (eventId) => {
        setEventsInternal(prev => prev.filter(event => event.id !== eventId));
    };

    // Clear all events
    // istanbul ignore next
    const clearEvents = () => {
        setEventsInternal([]);
    };

    // Refresh events function
    // istanbul ignore next
    const refreshEvents = () => {
        fetchEventData();
    };

    // Set up polling effect
    useEffect(() => {
        // Fetch from API on mount
        fetchEventData();

        // Poll for updates every 10 seconds
        const interval = setInterval(fetchEventData, 10000);
        return () => clearInterval(interval);
    }, []);

    // Helper functions
    const getTotalCount = () => events?.length || 0;
    const getEventsBySeverity = (severity) => events?.filter(event => event.severity === severity) || [];

    // Context value with computed properties
    // istanbul ignore next
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

// Export mock data and utility
export { mockEventData, ensureEventIds };