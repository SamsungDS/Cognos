import React from 'react';
import { FaRegChartBar} from 'react-icons/fa'
import { PiGaugeBold } from "react-icons/pi";
import { FaGears } from "react-icons/fa6";
import { HiOutlineDotsCircleHorizontal } from "react-icons/hi";
import { NavLink } from 'react-router-dom'

const SideBar = ({children}) => {

  const  menuItem = [
  {
    path:"/",
    icon: <PiGaugeBold/>,
    datatestid: 'menu-item-0',
  },
  {
    path:"/configure",
    icon: <FaGears/>,
    datatestid: 'menu-item-1',
  },
  {
    path:"/metrics",
    icon: <FaRegChartBar/>,
    datatestid: 'menu-item-2',
  },
  {
    path:"/about",
    icon: <HiOutlineDotsCircleHorizontal/>,
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
