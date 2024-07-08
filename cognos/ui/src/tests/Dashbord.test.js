import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Dashboard from '../pages/Dashboard';
import * as constants from '../constant';


describe('Dashboard', () => {
    test('renders correctly', () => {
      render(<Dashboard />);
      
      expect(screen.getByTestId('box-topology-id')).toBeInTheDocument();

      expect(screen.getByText(constants.hosts)).toBeInTheDocument();
      expect(screen.getByText(constants.CMM)).toBeInTheDocument();
      expect(screen.getByText(constants.racks)).toBeInTheDocument();


      
      const cmmDTexts = screen.getAllByText(constants.cmmd);
      expect(cmmDTexts.length).toBe(2);
      expect(screen.getByTestId('cmm-h')).toBeInTheDocument();
      expect(screen.getByText('1 TB')).toBeInTheDocument();
      expect(screen.getByText('0 GB')).toBeInTheDocument();

      expect(screen.getByText(constants.health)).toBeInTheDocument();
      

      const countZero = screen.getAllByText('0');
      expect(countZero.length).toBe(2);

      const countSix = screen.getAllByText('6');
      expect(countSix.length).toBe(2);

      const trendGraph = screen.getAllByText(constants.trend_graph);
      expect(trendGraph.length).toBe(2);
      
      expect(screen.getByTestId(constants.dramCxlMemUsage_id)).toBeInTheDocument();
    
    });
  });