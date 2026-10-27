import React from 'react';
import { Container, Row, Col} from 'react-bootstrap';
import BarIcon from "../assets/images/about/bar_icon.png";
import ChipTurningIcon from "../assets/images/about/chip_turning_icon.png";
import SymbolIcon from "../assets/images/about/symbol_icon.png";
import RackImage from "../assets/images/about/rack.png"
import './about.css'

const About = () => {
  return (
      <div className='Content content_root about' id='main-container'>
        <Container fluid >
            <Row className='heading-row'>
                <Col sm={12} md={6} lg={6} xl={6}> 
                    <div className='about-col-1' id='main-heading-info'>
                        <p className='about-heading' style={{fontFamily: 'Samsung'}}>Samsung <br/>Scalable Memory <br/>Solution*</p>
                        <div className='sub-heading' style={{fontFamily: 'Samsung'}}>
                            <p>&#8226; 1x Memory box with 6 CMM-D devices</p>
                            <p>&#8226; 3x EMR servers</p>
                            <p>&#8226; 1x CXL Fabric Manager server/client</p>
                        </div>
                    </div>
                </Col>
                <Col sm={12} md={6} lg={6} xl={6}>
                    <div className='about-col-2' id='mem-box-imgae'>
                        <img src={RackImage} alt="Header Mem Box"  className='rack-image' style={{ objectFit: 'contain', margin: 20, fontFamily: 'Samsung' }} />
                    </div>
                </Col>
            </Row>
            <Row>
                <Col sm={12} md={6} lg={4} xl={4}>
                    <div className='about-col-1' id='description-1'>
                        <article className='fs-22 description'>
                            <img src={SymbolIcon} alt="Symbol Icon" className='description-icon' style={{ objectFit: 'contain', margin: 20, marginLeft: 20, fontFamily: 'Samsung' }} /> <br/>
                            Composable memory <br/> infrastructure with memory <br/> pooling and sharing, all managed <br/> through robust and feature rich <br/> Samsung CXL Fabric Manager.  
                        </article>
                    </div>
                </Col>
                <Col sm={12} md={3} lg={4} xl={4}>
                   <div className='about-mid-col' id='description-2'>
                        <article className='fs-22 description'> 
                            <img src={ChipTurningIcon} alt="Chip Turning Icon" className='description-icon' style={{ objectFit: 'contain', margin: 20, marginLeft: 4, fontFamily: 'Samsung' }} /> <br/>
                            Heterogenous CXL <br/> memory support for <br/> CMM-D and CMM-H <br/> devices.
                        </article>
                   </div>
                </Col>
                <Col sm={12} md={3} lg={4} xl={4}>
                    <div className='about-col-3' id='description-3'>
                        <article className='fs-22 description'>
                            <img src={BarIcon} alt="Bar Icon" className='description-icon' style={{ objectFit: 'contain', margin: 20, marginLeft: 4, fontFamily: 'Samsung' }} /> <br/> 
                            Memory usage and <br/> analytics visualizations <br/> through Samsung CXL <br/> Fabric Manager.
                        </article>
                    </div>
                </Col>
            </Row>
        </Container>
      </div>
  )
}
export default About;