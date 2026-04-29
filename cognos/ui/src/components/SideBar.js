import React, { useContext } from 'react';
import { NavLink } from 'react-router-dom'
import { Cpu } from 'lucide-react';
import { ReactComponent as DashboardIcon } from '../assets/icons/DashboardIcon.svg';
import { ReactComponent as MetricsIcon } from '../assets/icons/ChartIcon.svg';
import { ReactComponent as AboutIcon } from '../assets/icons/AboutIcon.svg';
import { ReactComponent as AutotierIcon } from '../assets/icons/AutoTierIcon.svg';
import { ReactComponent as BeakerIcon } from '../assets/icons/Beaker.svg';
import { AuthContext } from './ProtectedRoute.js';
import NotificationBell from './NotificationBell';
import * as constants from '../constant';

// When login is disabled, treat everyone as admin (full access)
const RBAC_ENABLED = constants.Configs.rbac_enabled;
// Sider Bar Component is used for show navigation icon to pages
const SideBar = ({ children }) => {
  const auth = useContext(AuthContext);
  // If login is disabled, default to 'admin' so all menu items are visible
  const effectiveRole = RBAC_ENABLED ? (auth?.userRole) : 'admin';



  const menuItem = [
    {
      path: "/",
      icon: <DashboardIcon />,
      datatestid: 'menu-item-0',
      allowedRoles: ['admin', 'guest'],
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
    },
    {
      path: "/developer",
      icon: <BeakerIcon />,
      datatestid: 'menu-item-6',
      allowedRoles: ['admin', 'guest']
    }
  ];

  // Filter menu items based on effectiveRole
  const visibleMenuItems = menuItem.filter(item =>
    item.allowedRoles.includes(effectiveRole)
  );

  return (
    <>
      <div className='sidebar-container' style={{ width: "50px" }} id='side-bar-id' data-testid='sidebar-container'>
        <div style={{ width: "50px" }} className='sidebar'>
          {
            visibleMenuItems.map((item) => (
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
  );
}

export default SideBar;