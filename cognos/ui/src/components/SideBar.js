import React from 'react';
import { NavLink } from 'react-router-dom'
import { ReactComponent as ConfigureIcon  } from '../assets/icons/ConfigureIcon.svg';
import { ReactComponent as DashboardIcon  } from '../assets/icons/DashboardIcon.svg';
import { ReactComponent as MetricsIcon  } from '../assets/icons/ChartIcon.svg';
import { ReactComponent as AboutIcon  } from '../assets/icons/AboutIcon.svg';
import { ReactComponent as AutotierIcon } from '../assets/icons/AutoTierIcon.svg';

const SideBar = ({children}) => {

  const  menuItem = [
  {
    path:"/",
    icon: <DashboardIcon/>,
    datatestid: 'menu-item-0',
  },
  {
    path:"/configure",
    icon: <ConfigureIcon/>,
    datatestid: 'menu-item-1',
  },
  {
    path:"/metrics",
    icon: <MetricsIcon/>,
    datatestid: 'menu-item-2',
  },
  {
    path:"/jobs",
    icon: <AutotierIcon/>,
    datatestid: 'menu-item-4',
  },
  {
    path:"/about",
    icon: <AboutIcon/>,
    datatestid: 'menu-item-3',
  }
]
  return (
    <>
    <div className='sidebar-container' style={{width: "50px"}} id='side-bar-id' data-testid='sidebar-container'>
      <div style={{width: "50px"}} className='sidebar'>
         {
          menuItem.map((item, index) => (
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
