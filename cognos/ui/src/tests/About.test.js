import React from 'react';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import About from '../pages/About';

describe('About', () => {
  it('renders main heading and image', () => {
    const { getByText, getByAltText } = render(<About />);
    
    // Check if main heading is rendered
    expect(getByText('Samsung Scalable Memory Solution*')).toBeInTheDocument();

    // Check if image is rendered
    expect(getByAltText('Header Mem Box')).toBeInTheDocument();
  });

  it('renders description articles and icons', () => {
    const { getByText, getByAltText } = render(<About />);
    
    // Check if descriptions and icons are rendered
    expect(getByText('Composable memory infrastructure with memory pooling and sharing, all managed through robust and feature rich Samsung CXL Fabric Manager.')).toBeInTheDocument();
    expect(getByAltText('Symbol Icon')).toBeInTheDocument();

    expect(getByText('Heterogenous CXL memory support for CMM-D and CMM-H devices.')).toBeInTheDocument();
    expect(getByAltText('Chip Turning Icon')).toBeInTheDocument();

    expect(getByText('Memory usage and analytics visualizations through Samsung CXL Fabric Manager.')).toBeInTheDocument();
    expect(getByAltText('Bar Icon')).toBeInTheDocument();
  });
});