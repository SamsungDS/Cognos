import React, { useEffect, useState } from 'react';
import { Bell } from 'lucide-react';
import { useEvents } from '../contexts/EventsContext';
import './notificationBell.css';

const NotificationBell = () => {
  const { unreadCount, markAllAsRead } = useEvents(); // Use unreadCount instead of notificationCount
  const [isAnimating, setIsAnimating] = useState(false);
  const [prevCount, setPrevCount] = useState(0);

  const isDisabled = unreadCount === 0;

  // Trigger animation when new messages arrive (count increases)
  useEffect(() => {
    if (unreadCount > prevCount && unreadCount > 0) {
      setIsAnimating(true);
      setTimeout(() => setIsAnimating(false), 2000);
    }
    setPrevCount(unreadCount);
  }, [unreadCount]);

  // Periodic animation for persistent notifications
  useEffect(() => {
    if (isDisabled) return;

    const interval = setInterval(() => {
      setIsAnimating(true);
      setTimeout(() => setIsAnimating(false), 2000);
    }, 10000); // Every 10 seconds instead of 3

    return () => clearInterval(interval);
  }, [isDisabled]);

  // Mark all notifications as read when user clicks the bell
  // istanbul ignore next
  const handleBellClick = () => {
    if (isDisabled) return;

    setIsAnimating(false);
    markAllAsRead(); // This will reset the unread count to 0
  };

  return (
    <div
      className={`notification-bell d-inline-block ${isAnimating ? 'animating' : ''} ${isDisabled ? 'disabled' : ''}`}
      onClick={handleBellClick}
      role="button"
      tabIndex={0}
      onKeyPress={(e) => e.key === 'Enter' && handleBellClick()}
      aria-label={`${unreadCount} unread notifications`}
    >
      <Bell className={`bell-icon ${isAnimating ? 'pulse' : ''}`} />
      {unreadCount > 0 && (
        <>
          <span
            className={`notification-badge badge bg-danger text-white d-flex align-items-center justify-content-center ${isAnimating ? 'bounce' : ''}`}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
          {isAnimating && <span className="ping-ring"></span>}
        </>
      )}
    </div>
  );
};

export default NotificationBell;