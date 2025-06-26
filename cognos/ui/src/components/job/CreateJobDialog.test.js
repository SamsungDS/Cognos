import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import CreateJobDialog from './createJobDialog';


describe('Create Job Component', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onJobCreated: jest.fn()
  };


  beforeEach(() => {
    jest.clearAllMocks();

  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Rendering', () => {
    test('renders modal when isOpen is true', async () => {
      render(<CreateJobDialog {...defaultProps} />);
      
      expect(screen.getByText('SCMC Job Configuration')).toBeInTheDocument();
      expect(screen.getByText('Submit Job')).toBeInTheDocument();
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });

    test('does not render when isOpen is false', () => {
      render(<CreateJobDialog {...defaultProps} isOpen={false} />);
      
      expect(screen.queryByText('SCMC Job Configuration')).not.toBeInTheDocument();
    });

  });

});