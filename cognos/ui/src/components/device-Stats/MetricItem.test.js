import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import MetricItem from './MetricItem';

// Mock CSS import
jest.mock('./deviceCard.css', () => ({}));

describe('MetricItem Component', () => {
    describe('Rendering', () => {
        test('renders without crashing', () => {
            render(<MetricItem label="Test Metric" />);
            expect(screen.getByText('Test Metric')).toBeInTheDocument();
        });

        test('renders the label text correctly', () => {
            const testLabel = 'CXL Capacity';
            render(<MetricItem label={testLabel} />);
            expect(screen.getByText(testLabel)).toBeInTheDocument();
        });

        test('renders metric container with correct class', () => {
            const { container } = render(<MetricItem label="Test Metric" />);
            const metricDiv = container.querySelector('.metric');
            expect(metricDiv).toBeInTheDocument();
        });

        
    });



    describe('Text Styling', () => {
        test('applies correct text color to label', () => {
            render(<MetricItem label="Test Metric" />);
            const labelSpan = screen.getByText('Test Metric');
            expect(labelSpan).toHaveStyle({ color: '#00B3E3' });
        });

        test('applies correct font size to label', () => {
            render(<MetricItem label="Test Metric" />);
            const labelSpan = screen.getByText('Test Metric');
            expect(labelSpan).toHaveStyle({ fontSize: '14px' });
        });
    });

    describe('Edge Cases', () => {
        test('handles label with special characters', () => {
            const specialLabel = 'CXL@#$%Capacity';
            render(<MetricItem label={specialLabel} />);
            expect(screen.getByText(specialLabel)).toBeInTheDocument();
        });

        test('handles very long label text', () => {
            const longLabel = 'This is a very long metric label that should still render correctly';
            render(<MetricItem label={longLabel} />);
            expect(screen.getByText(longLabel)).toBeInTheDocument();
        });

        test('handles label with numbers', () => {
            const numericLabel = 'Metric 123';
            render(<MetricItem label={numericLabel} />);
            expect(screen.getByText(numericLabel)).toBeInTheDocument();
        });

        test('handles null label gracefully', () => {
            // This will render but might show empty
            const { container } = render(<MetricItem label={null} />);
            const metricDiv = container.querySelector('.metric');
            expect(metricDiv).toBeInTheDocument();
        });

        test('handles undefined label gracefully', () => {
            const { container } = render(<MetricItem label={undefined} />);
            const metricDiv = container.querySelector('.metric');
            expect(metricDiv).toBeInTheDocument();
        });
    });

    describe('Multiple Instances', () => {
        test('renders multiple MetricItems with different labels', () => {
            const { container } = render(
                <>
                    <MetricItem label="CXL Capacity" />
                    <MetricItem label="CXL Usage" />
                    <MetricItem label="CXL Bandwidth" />
                </>
            );

            expect(screen.getByText('CXL Capacity')).toBeInTheDocument();
            expect(screen.getByText('CXL Usage')).toBeInTheDocument();
            expect(screen.getByText('CXL Bandwidth')).toBeInTheDocument();

            const metrics = container.querySelectorAll('.metric');
            expect(metrics).toHaveLength(3);
        });

    });

 

    describe('Accessibility', () => {
        test('label text is accessible', () => {
            render(<MetricItem label="CXL Capacity" />);
            const label = screen.getByText('CXL Capacity');
            expect(label).toBeVisible();
        });

        test('component maintains semantic HTML structure', () => {
            const { container } = render(<MetricItem label="Test Metric" />);
            const spans = container.querySelectorAll('span');
            expect(spans).toHaveLength(1);
        });
    });



    describe('PropTypes Validation', () => {
        // Note: PropTypes validation only works in development mode
        test('component accepts string label prop', () => {
            expect(() => {
                render(<MetricItem label="Test Metric" />);
            }).not.toThrow();
        });
    });
});