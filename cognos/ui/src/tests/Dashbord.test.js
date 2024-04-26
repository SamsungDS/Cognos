import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/extend-expect';
import Dashboard from '../pages/Dashboard';
import * as constants from '../constant';


describe('Dashboard', () => {
    it('renders correctly', () => {
      render(<Dashboard />);
      
      expect(screen.getByTestId('box-topology-id')).toBeInTheDocument();

      expect(screen.getByText(constants.hosts)).toBeInTheDocument();
      expect(screen.getByText(constants.CMM)).toBeInTheDocument();
      expect(screen.getByText(constants.racks)).toBeInTheDocument();


      expect(screen.getByText(constants.sys_mem_allcated)).toBeInTheDocument();
      const cmmDTexts = screen.getAllByText(constants.cmmd);
      expect(cmmDTexts.length).toBe(3);
      expect(screen.getByText(constants.cmmh)).toBeInTheDocument();
      expect(screen.getByText('1 TB')).toBeInTheDocument();
      expect(screen.getByText('0 GB')).toBeInTheDocument();

      expect(screen.getByText(constants.health)).toBeInTheDocument();
      expect(screen.getByText(constants.host)).toBeInTheDocument();
      

      const countZero = screen.getAllByText('0');
      expect(countZero.length).toBe(4);

      const countSix = screen.getAllByText('6');
      expect(countSix.length).toBe(3);

      const trendGraph = screen.getAllByText(constants.trend_graph);
      expect(trendGraph.length).toBe(2);
      
      expect(screen.getByText(constants.system_bandwidth)).toBeInTheDocument();

      expect(screen.getByTestId(constants.rackBandwidth_id)).toBeInTheDocument();

      expect(screen.getByTestId(constants.dramCxlMemUsage_id)).toBeInTheDocument();
    
    });
  });