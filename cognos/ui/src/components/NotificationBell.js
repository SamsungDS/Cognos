import React, { useEffect, useState } from 'react';
import { Bell } from 'lucide-react';
import { useEvents } from '../contexts/EventsContext';
import './notificationBell.css';
const NotificationBell = () => {
  const { notificationCount } = useEvents();
  const [isAnimating, setIsAnimating] = useState(false);
  const isDisabled = notificationCount === 0;
  useEffect(() => {
    if (isDisabled) return;
    const interval = setInterval(() => {
      setIsAnimating(true);
      setTimeout(() => setIsAnimating(false), 2000);
    }, 3000);

    return () => clearInterval(interval);
  }, [isDisabled]);

  // istanbul ignore next
  const clearNotifications = () => {
    if (isDisabled) return;
    setIsAnimating(false);
  };

  return (
    <div
      className={`notification-bell d-inline-block ${isAnimating ? 'animating' : ''} ${isDisabled ? 'disabled' : ''}`}
      onClick={clearNotifications}
      role="button"
      tabIndex={0}
      onKeyPress={(e) => e.key === 'Enter' && clearNotifications()}

    >
      <Bell className={`bell-icon ${isAnimating ? 'pulse' : ''}`} />

      {notificationCount > 0 && (
        <>
          <span
            className={`notification-badge badge bg-danger text-white d-flex align-items-center justify-content-center ${isAnimating ? 'bounce' : ''}`}
          >
            {notificationCount > 10 ? '10+' : notificationCount}
          </span>

          {isAnimating && <span className="ping-ring"></span>}
        </>
      )}
    </div>
  );
};
export default NotificationBell;