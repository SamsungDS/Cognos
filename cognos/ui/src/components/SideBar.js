import React, { useContext } from 'react';
import { NavLink } from 'react-router-dom'
import { Cpu } from 'lucide-react';
import { ReactComponent as ConfigureIcon } from '../assets/icons/ConfigureIcon.svg';
import { ReactComponent as DashboardIcon } from '../assets/icons/DashboardIcon.svg';
import { ReactComponent as MetricsIcon } from '../assets/icons/ChartIcon.svg';
import { ReactComponent as AboutIcon } from '../assets/icons/AboutIcon.svg';
import { ReactComponent as AutotierIcon } from '../assets/icons/AutoTierIcon.svg';
import { AuthContext } from './ProtectedRoute.js';
import NotificationBell from './NotificationBell';
const SideBar = ({ children }) => {
  // Get userRole from AuthContext instead of props
  const { userRole } = useContext(AuthContext);

  const menuItem = [
    {
      path: "/",
      icon: <DashboardIcon />,
      datatestid: 'menu-item-0',
      allowedRoles: ['admin', 'guest'],
    },
    {
      path: "/configure",
      icon: <ConfigureIcon />,
      datatestid: 'menu-item-1',
      allowedRoles: ['admin']
    },
    {
      path: "/metrics",
      icon: <MetricsIcon />,
      datatestid: 'menu-item-2',
      allowedRoles: ['admin', 'guest']
    },
    {
      path: "/device-stats",
      icon: <Cpu />,
      datatestid: 'menu-item-6',
      allowedRoles: ['admin']
    },
    {
      path: "/application_view",
      icon: <AutotierIcon />,
      datatestid: 'menu-item-3',
      allowedRoles: ['admin']
    },
    {
      path: "/events",
      icon: <NotificationBell />,
      datatestid: 'menu-item-4',
      allowedRoles: ['admin']
    },
    {
      path: "/about",
      icon: <AboutIcon />,
      datatestid: 'menu-item-5',
      allowedRoles: ['admin', 'guest']
    }
  ]

  // Filter based on user role
  const visibleMenuItems = menuItem.filter(item =>
    item.allowedRoles.includes(userRole)
  );


  return (
    <>
      <div className='sidebar-container' style={{ width: "50px" }} id='side-bar-id' data-testid='sidebar-container'>
        <div style={{ width: "50px" }} className='sidebar'>
          {
            visibleMenuItems.map((item, index) => (
              <NavLink to={item.path} key={item.datatestid} activeclassname="active" className="link">
                <div className='icon' data-testid={item.datatestid}>
                  {item.icon}
                </div>
              </NavLink>
            ))
          }
        </div>
      </div>
      {children}
    </>
  )
}

export default SideBar;