import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { AlertTriangle, CheckCircle, Info, X, Bell, Search, ShieldAlert, Clock, Trash2, RefreshCw } from 'lucide-react';
import './events.css';
import { useEvents } from '../contexts/EventsContext';

const Events = () => {
    const { events, setEvents } = useEvents();
    const [selectedFilter, setSelectedFilter] = useState('all');
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedEvents, setSelectedEvents] = useState([]);
    const [showDetails, setShowDetails] = useState(null);

    const severityConfig = {
        critical: {
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
        info: {
            icon: Info,
            color: 'rgb(59, 130, 246)',
            bg: 'rgb(239, 246, 255)',
            border: 'rgb(147, 197, 253)',
            text: 'rgb(30, 64, 175)'
        }
    };

    const filterOptions = [
        { value: 'all', label: 'All Events', count: events.length },
        { value: 'critical', label: 'Critical', count: events.filter(e => e.severity === 'critical').length },
        { value: 'warning', label: 'Warnings', count: events.filter(e => e.severity === 'warning').length },
        { value: 'info', label: 'Info', count: events.filter(e => e.severity === 'info').length }
    ];

    const filteredEvents = events.filter(event => {
        const matchesFilter = selectedFilter === 'all' || event.severity === selectedFilter;
        const matchesSearch = event.event_name.toLowerCase().includes(searchTerm.toLowerCase());
        return matchesFilter && matchesSearch;
    });

    const dismissEvent = (eventId) => {
        setEvents(events.filter(event => event.id !== eventId));
        setSelectedEvents(selectedEvents.filter(id => id !== eventId));
    };

    const toggleSelectEvent = (eventId) => {
        setSelectedEvents(prev =>
            prev.includes(eventId)
                ? prev.filter(id => id !== eventId)
                : [...prev, eventId]
        );
    };

    const clearSelectedEvents = () => {
        setEvents(events.filter(event => !selectedEvents.includes(event.id)));
        setSelectedEvents([]);
    };

    const clearAllEvents = () => {
        if (selectedFilter === 'all') {
            setEvents([]);
        } else {
            setEvents(events.filter(event => event.severity !== selectedFilter));
        }
        setSelectedEvents([]);
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
                <span style={{ fontSize: '0.75rem', fontWeight: '600', textTransform: 'capitalize' }}>
                    {severity}
                </span>
            </div>
        );
    };

    const EventCard = ({ event }) => {
        const config = severityConfig[event.severity];
        const isSelected = selectedEvents.includes(event.id);

        return (
            <div
                className="card mb-3 shadow-sm border-4"
                style={{
                    borderLeft: `4px solid ${config.color}`,
                    backgroundColor: isSelected ? '#57595aff' : '#5b646dff',
                    transition: 'all 0.2s ease',
                    cursor: 'pointer',
                    height: '110px'
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
                                    {event.event_msg}
                                </h6>

                                <div className="d-flex flex-wrap gap-2 mb-2">
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Event Name:</strong> {event.event_name}
                                    </span>
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Source:</strong> {event.source}
                                    </span>
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Source type:</strong> {event.source_type}
                                    </span>
                                    <span className="events-page-badge events-page-text-dark events-page-border" style={{ fontSize: '0.7rem' }}>
                                        <strong>Node:</strong> {event.node_name}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div className="d-flex align-items-center gap-2">
                            <button
                                onClick={() => setShowDetails(showDetails === event.id ? null : event.id)}
                                className="btn btn-sm btn-outline-primary-refresh"
                                style={{ fontSize: '0.75rem' }}
                                disabled
                            >
                                Action
                            </button>
                            <button
                                onClick={() => dismissEvent(event.id)}
                                className="btn btn-sm btn-outline-danger d-flex align-items-center"
                                title="Dismiss event"
                            >
                                <X size={14} />
                            </button>
                        </div>
                    </div>

                    {showDetails === event.id && (
                        <div className="mt-3 pt-3 border-top">
                            <div className="row g-3">
                                <div className="col-md-6">
                                    <div className="bg-light p-2 rounded">
                                        <small className="text-muted d-block">Category</small>
                                        <span style={{ fontSize: '0.9rem', fontWeight: '500' }}>{event.category}</span>
                                    </div>
                                </div>
                                <div className="col-md-6">
                                    <div className="bg-light p-2 rounded">
                                        <small className="text-muted d-block">Full Source Path</small>
                                        <span style={{ fontSize: '0.9rem', fontWeight: '500' }}>{event.source} → {event.source_type}</span>
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
            event_msg: PropTypes.string.isRequired,
            event_name: PropTypes.string.isRequired,
            source: PropTypes.string.isRequired,
            source_type: PropTypes.string.isRequired,
            node_name: PropTypes.string.isRequired,
            category: PropTypes.string.isRequired,
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

                    <div className="d-flex align-items-center gap-3">
                        <button
                            className="btn btn-outline-primary-refresh memory-box-title d-flex align-items-center"
                            onClick={() => setEvents()}
                            disabled
                        >
                            <RefreshCw size={16} className="me-2" />
                            Refresh
                        </button>

                        {selectedEvents.length > 0 && (
                            <button
                                className="btn btn-danger d-flex align-items-center"
                                onClick={clearSelectedEvents}
                            >
                                <Trash2 size={16} className="me-2" />
                                Clear Selected ({selectedEvents.length})
                            </button>
                        )}
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
                                        width:'21rem',
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
                                            <div className="text-muted" style={{ fontSize: '0.9rem' }}>
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

                            <div className="col-md-6 text-end">
                                <button
                                    className="btn btn-outline-danger"
                                    onClick={clearAllEvents}
                                    disabled={filteredEvents.length === 0}
                                >
                                    Clear {selectedFilter === 'all' ? 'All' : selectedFilter} Events
                                </button>
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