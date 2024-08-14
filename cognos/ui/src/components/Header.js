import React from 'react'
import SamsungLogo from '../assets/images/logos/samsung_logo_lettermark_white.PNG'

const Header = () => {
  return (
      <div className="Header" id='header-container-id'>
        <header className='heading'>
            <div style={{display:'flex'}}><img src={SamsungLogo} alt="logo" style={{ objectFit: 'contain', width: 180, margin: 20 }} />  <span className='fs-22' style={{marginTop:18, fontSize: 24}}> | &nbsp; &nbsp; Cognos Management Console</span></div>
        </header>
      </div>
  )
}

export default Header;