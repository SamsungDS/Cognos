import React, { useContext, useState, useEffect, createContext, useMemo } from 'react';
import * as constants from '../constant';

// Mock data - moved to top for better organization
const mockEventData = [];

// Utility function to parse timestamp to Date object for comparison
// istanbul ignore next
const parseTimestamp = (timestamp) => {
    if (!timestamp) return new Date();

    // Handle ISO 8601 format
    if (timestamp.includes('T') || timestamp.includes('Z')) {
        return new Date(timestamp);
    }

    // Handle time-only format (HH:MM:SS) - use today's date
    if (/^\d{2}:\d{2}:\d{2}$/.test(timestamp)) {
        const today = new Date();
        const [hours, minutes, seconds] = timestamp.split(':').map(Number);
        today.setHours(hours, minutes, seconds, 0);
        return today;
    }

    // Try to parse as standard date string
    const parsed = new Date(timestamp);
    return isNaN(parsed.getTime()) ? new Date() : parsed;
};

// Sort events by timestamp (newest first)
// istanbul ignore next
const sortEventsByTime = (eventsArray) => {
    if (!Array.isArray(eventsArray)) return [];

    return [...eventsArray].sort((a, b) => {
        const dateA = parseTimestamp(a.timestamp);
        const dateB = parseTimestamp(b.timestamp);
        return dateB.getTime() - dateA.getTime(); // Descending order (newest first)
    });
};

// Generate unique event signature for tracking (based on content, not just ID)
// istanbul ignore next
const generateEventSignature = (event) => {
    // Create a signature based on event content that won't change
    const signatureData = {
        timestamp: event.timestamp,
        msg: event.msg,
        cluster_name: event.cluster_name,
        node_name: event.node_name,
        severity: event.severity,
        domain: event.domain
    };
    return JSON.stringify(signatureData);
};

// Utility function to ensure all events have unique IDs and are sorted by time
// istanbul ignore next
const ensureEventIds = (eventsArray, seenSignatures = new Set()) => {
    if (!Array.isArray(eventsArray)) return [];

    const eventsWithIds = eventsArray.map((event, index) => {
        const signature = generateEventSignature(event);
        const wasSeenBefore = seenSignatures.has(signature);

        return {
            ...event,
            // eslint-disable-next-line no-restricted-syntax
            id: event.id || `event-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 11)}`,
            signature: signature,
            isRead: event.isRead !== undefined ? event.isRead : wasSeenBefore // Keep existing or mark based on signature
        };
    });

    // Sort by time after adding IDs
    return sortEventsByTime(eventsWithIds);
};

// Create Events Context with default values
export const EventsContext = createContext({
    events: [],
    setEvents: () => { },
    isLoading: false,
    error: null,
    notificationCount: 0,
    unreadCount: 0,
    hasEvents: false,
    eventCount: 0,
    criticalEvents: [],
    warningEvents: [],
    infoEvents: [],
    errorEvents: [],
    addEvent: () => { },
    removeEvent: () => { },
    clearEvents: () => { },
    refreshEvents: () => { },
    markAllAsRead: () => { },
    markAsRead: () => { },
    getUnreadEvents: () => []
});

// Events Provider Component
export const EventsProvider = ({ children }) => {
    // Track signatures of all events we've ever seen (persists across fetches)
    const [seenEventSignatures, setSeenEventSignatures] = useState(new Set());

    // eslint-disable-next-line react/hook-use-state
    const [events, setEventsInternal] = useState(() => {
        const initialEvents = ensureEventIds(mockEventData, new Set());
        // Mark initial mock data as seen
        const signatures = new Set(initialEvents.map(e => e.signature));
        setSeenEventSignatures(signatures);
        return initialEvents;
    });

    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const apiEndpoint = constants.Configs.api_endpoint;

    // Wrapper for setEvents that ensures IDs and sorts by time
    // istanbul ignore next
    const setEvents = (eventsOrUpdater) => {
        if (typeof eventsOrUpdater === 'function') {
            setEventsInternal(prev => {
                const newEvents = eventsOrUpdater(prev);
                return ensureEventIds(newEvents, seenEventSignatures);
            });
        } else {
            setEventsInternal(ensureEventIds(eventsOrUpdater, seenEventSignatures));
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

            // Process new events and preserve read status
            setEventsInternal(prevEvents => {
                // Create a map of existing events by signature for quick lookup
                const existingEventMap = new Map();
                prevEvents.forEach(event => {
                    if (event.signature) {
                        existingEventMap.set(event.signature, event);
                    }
                });

                // Process incoming events
                const processedEvents = eventsData.map((event, index) => {
                    const signature = generateEventSignature(event);
                    const existingEvent = existingEventMap.get(signature);
                    const wasSeenBefore = seenEventSignatures.has(signature);

                    return {
                        ...event,
                        // eslint-disable-next-line no-restricted-syntax
                        id: event.id || existingEvent?.id || `event-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 11)}`,
                        signature: signature,
                        // If we have seen this exact event before (by signature), preserve its read status
                        // If it's completely new (not in seenEventSignatures), mark as unread
                        isRead: existingEvent ? existingEvent.isRead : wasSeenBefore
                    };
                });

                return sortEventsByTime(processedEvents);
            });

        } catch (error) {
            console.error('Error fetching event data:', error);
            setError(error.message);
            // Keep existing events on error instead of setting to null
        } finally {
            setIsLoading(false);
        }
    };

    // Add new event function - automatically maintains time-based sorting
    // istanbul ignore next
    const addEvent = (newEvent) => {
        const signature = generateEventSignature(newEvent);
        const event = {
            ...newEvent,
            // eslint-disable-next-line no-restricted-syntax
            id: newEvent.id || `event-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
            timestamp: newEvent.timestamp || new Date().toISOString(),
            signature: signature,
            isRead: false // New events are always unread
        };

        // Add new event and re-sort to maintain time order
        setEventsInternal(prev => sortEventsByTime([event, ...prev]));
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
        // Don't clear seenEventSignatures - we want to remember what we've seen
    };

    // Mark all events as read and update seen signatures
    // istanbul ignore next
    const markAllAsRead = () => {
        setEventsInternal(prev => {
            const updatedEvents = prev.map(event => ({ ...event, isRead: true }));

            // Add all current event signatures to seen set
            const newSignatures = new Set(seenEventSignatures);
            updatedEvents.forEach(event => {
                if (event.signature) {
                    newSignatures.add(event.signature);
                }
            });
            setSeenEventSignatures(newSignatures);

            return updatedEvents;
        });
    };

    // Mark specific event as read and update seen signatures
    // istanbul ignore next
    const markAsRead = (eventId) => {
        setEventsInternal(prev => {
            const updatedEvents = prev.map(event => {
                if (event.id === eventId) {
                    // Add this event's signature to seen set
                    if (event.signature) {
                        setSeenEventSignatures(prev => new Set([...prev, event.signature]));
                    }
                    return { ...event, isRead: true };
                }
                return event;
            });
            return updatedEvents;
        });
    };

    // Get only unread events
    // istanbul ignore next
    const getUnreadEvents = () => {
        return events?.filter(event => !event.isRead) || [];
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
    const getUnreadCount = () => events?.filter(event => !event.isRead).length || 0;
    const getEventsBySeverity = (severity) => {
        const filtered = events?.filter(event => event.severity === severity) || [];
        return sortEventsByTime(filtered);
    };

    // Context value with computed properties - memoized to prevent unnecessary re-renders
    // istanbul ignore next
    const contextValue = useMemo(() => ({
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
        markAllAsRead,
        markAsRead,
        getUnreadEvents,

        // Computed values
        notificationCount: getTotalCount(),
        unreadCount: getUnreadCount(),
        hasEvents: events && events.length > 0,
        eventCount: events?.length || 0,
        criticalEvents: getEventsBySeverity('critical'),
        warningEvents: getEventsBySeverity('warning'),
        infoEvents: getEventsBySeverity('info'),
        errorEvents: getEventsBySeverity('error')
    }), [events, isLoading, error]);

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