import React from 'react';
import { Container, Row, Col} from 'react-bootstrap';
import './Developer.css'

const Developer = () => {
  return (
      <div className='Content content_root about' id='main-container'>
        <h1>
            Experimental Page
        </h1>
        <h2>
            Use this page to test unique features of Cognos.
            Add key-value pairs for each arg typically required in the "command_params" map per the feature
        </h2>
      </div>
  )
}
export default Developer;