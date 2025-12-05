import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { AlertTriangle, CheckCircle, Info, Bell, Search, ShieldAlert, Clock, RefreshCw, ChevronDown, ChevronUp, Calendar } from 'lucide-react';
import './events.css';
import { useEvents } from '../contexts/EventsContext';

const Events = () => {
    const { events, setEvents } = useEvents();
    const [selectedFilter, setSelectedFilter] = useState('all');
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedEvents, setSelectedEvents] = useState([]);
    const [expandedEvent, setExpandedEvent] = useState(null);

    const severityConfig = {
        critical: {
            icon: ShieldAlert,
            color: 'rgb(239, 68, 68)',
            bg: 'rgb(254, 242, 242)',
            border: 'rgb(252, 165, 165)',
            text: 'rgb(153, 27, 27)'
        },
        failed: {
            icon: ShieldAlert,
            color: 'rgb(239, 68, 68)',
            bg: 'rgb(254, 242, 242)',
            border: 'rgb(252, 165, 165)',
            text: 'rgb(153, 27, 27)'
        },
        warning: {
            icon: AlertTriangle,
            color: 'rgb(245, 158, 11)',
            bg: 'rgb(255, 251, 235)',
            border: 'rgb(253, 230, 138)',
            text: 'rgb(146, 64, 14)'
        },
        degraded: {
            icon: AlertTriangle,
            color: 'rgb(245, 158, 11)',
            bg: 'rgb(255, 251, 235)',
            border: 'rgb(253, 230, 138)',
            text: 'rgb(146, 64, 14)'
        },
        info: {
            icon: Info,
            color: 'rgb(59, 130, 246)',
            bg: 'rgb(239, 246, 255)',
            border: 'rgb(147, 197, 253)',
            text: 'rgb(30, 64, 175)'
        },
        Normal: {
            icon: Info,
            color: 'rgb(59, 130, 246)',
            bg: 'rgb(239, 246, 255)',
            border: 'rgb(147, 197, 253)',
            text: 'rgb(30, 64, 175)'
        },
        good: {
            icon: Info,
            color: 'rgb(59, 130, 246)',
            bg: 'rgb(239, 246, 255)',
            border: 'rgb(147, 197, 253)',
            text: 'rgb(30, 64, 175)'
        },
        error: {
            icon: AlertTriangle,
            color: 'rgba(245, 27, 11, 1)',
            bg: 'rgba(207, 173, 173, 1)',
            border: 'rgba(218, 46, 23, 1)',
            text: 'rgb(146, 64, 14)'
        },
    };

    // Severity grouping for filtering and counting
    const severityGroups = {
        critical: ['critical', 'failed'],
        warning: ['warning', 'degraded'],
        info: ['info', 'Normal', 'good'],
        error: ['error']
    };

    // Helper function to check if an event matches a filter group
    const eventMatchesFilterGroup = (eventSeverity, filterValue) => {
        if (filterValue === 'all') return true;
        return severityGroups[filterValue]?.includes(eventSeverity) || false;
    };

    // Calculate counts for each filter group
    const getFilterCount = (filterValue) => {
        if (filterValue === 'all') return events.length;
        return events.filter(e => eventMatchesFilterGroup(e.severity, filterValue)).length;
    };

    const filterOptions = [
        { value: 'all', label: 'All Events', count: getFilterCount('all') },
        { value: 'critical', label: 'Critical', count: getFilterCount('critical') },
        { value: 'warning', label: 'Warnings', count: getFilterCount('warning') },
        { value: 'info', label: 'Info', count: getFilterCount('info') },
        { value: 'error', label: 'Error', count: getFilterCount('error') }
    ];

    // Updated filtering logic to use severity groups
    const filteredEvents = events.filter(event => {
        const matchesFilter = eventMatchesFilterGroup(event.severity, selectedFilter);
        const matchesSearch = event.node_name.toLowerCase().includes(searchTerm.toLowerCase());
        return matchesFilter && matchesSearch;
    });

    const toggleSelectEvent = (eventId) => {
        setSelectedEvents(prev =>
            prev.includes(eventId)
                ? prev.filter(id => id !== eventId)
                : [...prev, eventId]
        );
    };

    const toggleEventExpansion = (eventId) => {
        setExpandedEvent(expandedEvent === eventId ? null : eventId);
    };

    const getSeverityBadge = (severity) => {
        const config = severityConfig[severity];
        const IconComponent = config.icon;

        return (
            <div
                className="d-flex align-items-center px-2 py-1 rounded-pill"
                style={{
                    backgroundColor: config.bg,
                    border: `1px solid ${config.border}`,
                    color: config.text
                }}
            >
                <IconComponent size={12} className="me-1" />
                <span style={{ fontSize: '0.75rem', fontWeight: '600', textTransform: 'capitalize', color: `${config.text}` }}>
                    {severity}
                </span>
            </div>
        );
    };

    const EventCard = ({ event }) => {
        const config = severityConfig[event.severity];
        const isSelected = selectedEvents.includes(event.id);
        const isExpanded = expandedEvent === event.id;

        return (
            <div
                className="card mb-3 shadow-sm border-4"
                style={{
                    borderLeft: `4px solid ${config.color}`,
                    backgroundColor: isSelected ? '#57595aff' : '#5b646dff',
                    transition: 'all 0.3s ease',
                    minHeight: isExpanded ? 'auto' : '110px'
                }}
                onMouseEnter={(e) => e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'}
                onMouseLeave={(e) => e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)'}
            >
                <div className="card-body p-1">
                    <div className="d-flex align-items-start justify-content-between">
                        <div className="d-flex align-items-start flex-grow-1">
                            <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => toggleSelectEvent(event.id)}
                                className="form-check-input me-3 mt-1"
                                style={{ cursor: 'pointer' }}
                            />

                            <div className="flex-grow-1">
                                <div className="d-flex align-items-center mb-2">
                                    {getSeverityBadge(event.severity)}
                                    <span className="text-white ms-2 d-flex align-items-center" style={{ fontSize: '0.8rem' }}>
                                        <Clock size={12} className="me-1" />
                                        {event.timestamp}
                                    </span>
                                </div>

                                <h6 className="card-title mb-2 text-white" style={{ fontSize: '1rem', fontWeight: '600' }}>
                                    {event.msg}
                                </h6>

                                <div className="d-flex flex-wrap gap-2 mb-2">
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Source:</strong> {event.source}
                                    </span>
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Source type:</strong> {event.source_type}
                                    </span>
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Node:</strong> {event.node_name}
                                    </span>
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Cluster Name:</strong> {event.cluster_name}
                                    </span>
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Category:</strong> {event.category}
                                    </span>
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Domain:</strong> {event.domain}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div className="d-flex align-items-center gap-2">
                            <button
                                onClick={() => toggleEventExpansion(event.id)}
                                className="btn btn-sm btn-outline-primary-refresh d-flex align-items-center"
                                style={{ fontSize: '0.75rem', minWidth: '80px' }}
                                title={isExpanded ? "Collapse details" : "Expand details"}
                            >
                                {isExpanded ? (
                                    <>
                                        <ChevronUp size={14} className="me-1" />
                                        Collapse
                                    </>
                                ) : (
                                    <>
                                        <ChevronDown size={14} className="me-1" />
                                        Details
                                    </>
                                )}
                            </button>
                        </div>
                    </div>

                    {isExpanded && (
                        <div
                            className="mt-3 pt-3 border-top"
                            style={{
                                animation: 'fadeIn 0.3s ease-in-out',
                                borderColor: 'rgba(255,255,255,0.1)'
                            }}
                        >
                            <div className="row g-3">
                                <div className="col-12">
                                    <div
                                        className="p-3 rounded"
                                        style={{
                                            backgroundColor: 'rgba(255,255,255,0.05)',
                                            border: '1px solid rgba(255,255,255,0.1)'
                                        }}
                                    >
                                        <div className="d-flex align-items-center mb-2">
                                            <Calendar size={16} className="text-white me-2" />
                                            <small className="text-white-50 fw-bold">Event Details</small>
                                        </div>
                                        <div className="text-white" style={{ fontSize: '0.85rem', lineHeight: '1.5' }}>
                                            <p className="mb-2"><strong>Payload:</strong> {JSON.stringify(event.payload)}</p>
                                            <p className="mb-2"><strong>Timestamp:</strong> {event.timestamp}</p>
                                            <p className="mb-0"><strong>Severity Level:</strong> <span style={{ textTransform: 'uppercase' }}>{event.severity}</span></p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        );
    };

    EventCard.propTypes = {
        event: PropTypes.shape({
            id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
            severity: PropTypes.string.isRequired,
            timestamp: PropTypes.string.isRequired,
            msg: PropTypes.string.isRequired,
            source: PropTypes.string.isRequired,
            source_type: PropTypes.string.isRequired,
            node_name: PropTypes.string.isRequired,
            category: PropTypes.string.isRequired,
            domain: PropTypes.string.isRequired,
            cluster_name: PropTypes.string.isRequired,
            payload: PropTypes.string.isRequired
        }).isRequired,
    };

    return (
        <div className="custom-container">
            {/* Header */}
            <div className="container-fluid px-4 py-4">
                <div className="d-flex align-items-center justify-content-between px-2 py-2 rounded" style={{ backgroundColor: '#212529' }}>
                    <div>
                        <h2 className="mb-1 memory-box-title px-0" style={{ fontWeight: '700' }}>
                            <Bell className="me-2 memory-box-title" size={28} />
                            System Events
                        </h2>
                        <p className="text-white mb-0" style={{ fontSize: '0.9rem' }}>
                            Monitor and manage system events
                        </p>
                    </div>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="container-fluid px-4 py-4">
                <div className="row g-4 mb-4">
                    {filterOptions.filter(f => f.value !== 'all').map((option) => {
                        const config = severityConfig[option.value];
                        return (
                            <div key={option.value} className="col-md-3 col-sm-6">
                                <button
                                    className="card border-4 shadow-sm h-100"
                                    style={{
                                        width: '21rem',
                                        borderLeft: `4px solid ${config.color}`,
                                        cursor: 'pointer',
                                        backgroundColor: selectedFilter === option.value ? config.bg : '#d7d2d2'
                                    }}
                                    onClick={() => setSelectedFilter(selectedFilter === option.value ? 'all' : option.value)}
                                >
                                    <div className="card-body d-flex align-items-center">
                                        <div
                                            className="p-3 rounded-circle me-3"
                                            style={{ backgroundColor: config.bg }}
                                        >
                                            <config.icon size={24} style={{ color: config.color }} />
                                        </div>
                                        <div>
                                            <div className="h4 mb-0 fw-bold" style={{ color: config.color }}>
                                                {option.count}
                                            </div>
                                            <div style={{ fontSize: '0.9rem', color: config.color }}>
                                                {option.label}
                                            </div>
                                        </div>
                                    </div>
                                </button>
                            </div>
                        );
                    })}
                </div>

                {/* Search and Filter Bar */}
                <div className="card card-events mb-4">
                    <div className="card-body rounded-0" style={{ backgroundColor: '#212529' }}>
                        <div className="row g-2 align-items-center">
                            <div className="col-md-6">
                                <select
                                    className="form-select"
                                    value={selectedFilter}
                                    onChange={(e) => setSelectedFilter(e.target.value)}
                                    style={{ fontSize: '0.9rem' }}
                                >
                                    {filterOptions.map((option) => (
                                        <option key={option.value} value={option.value}>
                                            {option.label} ({option.count})
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Events List */}
                <div className="row">
                    <div className="col-12">
                        {filteredEvents.length > 0 ? (
                            <div className="card border-4 shadow-sm">
                                <div className="card-header border-bottom d-flex align-items-center justify-content-between py-3" style={{ backgroundColor: "#212529" }}>
                                    <h5 className="mb-0 text-white">
                                        {filteredEvents.length} Event{filteredEvents.length !== 1 ? 's' : ''} Found
                                        {selectedFilter !== 'all' && (
                                            <span className="events-page-badge events-page-text-dark events-page-border ms-2" style={{ fontSize: '0.7rem' }}>
                                                {selectedFilter}
                                            </span>
                                        )}
                                    </h5>

                                    {filteredEvents.length > 0 && (
                                        <div className="text-white" style={{ fontSize: '0.85rem' }}>
                                            {selectedEvents.length > 0 && `${selectedEvents.length} selected`}
                                            {expandedEvent && " • 1 expanded"}
                                        </div>
                                    )}
                                </div>

                                <div
                                    className="card-body p-0"
                                    style={{
                                        maxHeight: '300px',
                                        overflowY: 'auto',
                                        overflowX: 'hidden',
                                        backgroundColor: "#212529"
                                    }}
                                >
                                    <div className="p-3">
                                        {filteredEvents.map((event) => (
                                            <EventCard key={event.id} event={event} />
                                        ))}
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="card border-4 shadow-sm">
                                <div className="card-body text-center py-5">
                                    <div
                                        className="mx-auto mb-3 rounded-circle d-flex align-items-center justify-content-center"
                                        style={{ width: '80px', height: '80px', backgroundColor: '#212529' }}
                                    >
                                        {events.length === 0 ? (
                                            <CheckCircle size={40} className="text-success" />
                                        ) : (
                                            <Search size={40} className="text-white" />
                                        )}
                                    </div>

                                    <h4 className="text-dark mb-2">
                                        {events.length === 0 ? 'All Clear!' : 'No Events Found'}
                                    </h4>

                                    <p className="text-muted mb-0">
                                        {events.length === 0
                                            ? 'There are no active events at this time. Your system is running smoothly.'
                                            : `No events match your current filter "${selectedFilter}" or search term "${searchTerm}".`
                                        }
                                    </p>

                                    {events.length > 0 && (searchTerm || selectedFilter !== 'all') && (
                                        <button
                                            className="btn btn-outline-primary-refresh memory-box-title mt-3"
                                            onClick={() => {
                                                setSearchTerm('');
                                                setSelectedFilter('all');
                                            }}
                                        >
                                            Clear Filters
                                        </button>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
export default Events;