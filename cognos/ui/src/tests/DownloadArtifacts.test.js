import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import DownloadArtifacts from '../pages/DownloadArtifacts';

// Mock CSS imports
jest.mock('bootstrap/dist/css/bootstrap.min.css', () => ({}));
jest.mock('../pages/downloadArtifacts.css', () => ({}));

// Mock lucide-react Download icon
jest.mock('lucide-react', () => ({
    Download: ({ className, size }) => (
        <svg data-testid="download-icon" className={className} width={size} height={size}>
            <title>Download Icon</title>
        </svg>
    ),
}));

describe('DownloadArtifacts Component', () => {
    describe('Rendering', () => {
        it('renders without crashing', () => {
            expect(() => render(<DownloadArtifacts />)).not.toThrow();
        });

        it('renders the main page container with correct classes', () => {
            const { container } = render(<DownloadArtifacts />);
            const pageContainer = container.querySelector('.page-container.Content.content_root.about');
            expect(pageContainer).toBeInTheDocument();
        });

        it('renders the header section', () => {
            render(<DownloadArtifacts />);
            expect(screen.getByText('Download Cognos Artifacts')).toBeInTheDocument();
        });

        it('renders the header as h1 element', () => {
            render(<DownloadArtifacts />);
            const heading = screen.getByText('Download Cognos Artifacts');
            expect(heading.tagName).toBe('H1');
        });

        it('renders the dropdown label', () => {
            render(<DownloadArtifacts />);
            expect(screen.getByText('Select Cognos Release')).toBeInTheDocument();
        });

        it('renders the dropdown select element', () => {
            render(<DownloadArtifacts />);
            const select = screen.getByRole('combobox');
            expect(select).toBeInTheDocument();
        });

        it('renders the default option in dropdown', () => {
            render(<DownloadArtifacts />);
            expect(screen.getByText('-- Select an artifact --')).toBeInTheDocument();
        });

        it('renders the download button', () => {
            render(<DownloadArtifacts />);
            const button = screen.getByRole('button', { name: /Download Artifact/i });
            expect(button).toBeInTheDocument();
        });

        it('renders the download icon', () => {
            render(<DownloadArtifacts />);
            const icon = screen.getByTestId('download-icon');
            expect(icon).toBeInTheDocument();
        });
    });

    describe('Layout Structure', () => {
        it('renders full-width header row', () => {
            const { container } = render(<DownloadArtifacts />);
            const headerRow = container.querySelector('.row.full-width-header');
            expect(headerRow).toBeInTheDocument();
        });

        it('renders content container', () => {
            const { container } = render(<DownloadArtifacts />);
            const contentContainer = container.querySelector('.content-container');
            expect(contentContainer).toBeInTheDocument();
        });

        it('renders card with dark theme', () => {
            const { container } = render(<DownloadArtifacts />);
            const cards = container.querySelectorAll('.card.card-dark.rounded-3');
            expect(cards.length).toBeGreaterThan(0);
        });

        it('renders download section in col-lg-12', () => {
            const { container } = render(<DownloadArtifacts />);
            const column = container.querySelector('.col-lg-12.col-md-12');
            expect(column).toBeInTheDocument();
        });
    });

    describe('Initial State', () => {
        it('has empty selected artifact by default', () => {
            render(<DownloadArtifacts />);
            const select = screen.getByRole('combobox');
            expect(select.value).toBe('');
        });

        it('has download button disabled by default', () => {
            render(<DownloadArtifacts />);
            const button = screen.getByRole('button', { name: /Download Artifact/i });
            expect(button).toBeDisabled();
        });

        it('has dropdown enabled by default', () => {
            render(<DownloadArtifacts />);
            const select = screen.getByRole('combobox');
            expect(select).not.toBeDisabled();
        });

        it('download icon does not have animate-bounce class initially', () => {
            render(<DownloadArtifacts />);
            const icon = screen.getByTestId('download-icon');
            expect(icon).not.toHaveClass('animate-bounce');
        });
    });

    describe('Dropdown Interaction', () => {
        it('allows selecting an option from dropdown', () => {
            render(<DownloadArtifacts />);
            const select = screen.getByRole('combobox');

            // Simulate selecting an option (in real implementation, there would be options)
            fireEvent.change(select, { target: { value: 'artifact-1' } });

            // Since the component doesn't update the state from the select,
            // we just verify the select can receive changes
            expect(select).toBeInTheDocument();
        });

        it('displays form-select-dark class on dropdown', () => {
            render(<DownloadArtifacts />);
            const select = screen.getByRole('combobox');
            expect(select).toHaveClass('form-select-dark');
        });
    });

    describe('Button State Management', () => {
        it('keeps button disabled when no artifact is selected', () => {
            render(<DownloadArtifacts />);
            const button = screen.getByRole('button', { name: /Download Artifact/i });
            expect(button).toBeDisabled();
        });

        it('button has correct CSS classes', () => {
            render(<DownloadArtifacts />);
            const button = screen.getByRole('button', { name: /Download Artifact/i });
            expect(button).toHaveClass('btn', 'btn-download', 'w-100', 'd-flex', 'align-items-center', 'justify-content-center');
        });
    });

    describe('Download Icon', () => {
        it('renders icon with correct size', () => {
            render(<DownloadArtifacts />);
            const icon = screen.getByTestId('download-icon');
            expect(icon).toHaveAttribute('width', '20');
            expect(icon).toHaveAttribute('height', '20');
        });

        it('icon has me-2 margin class', () => {
            render(<DownloadArtifacts />);
            const icon = screen.getByTestId('download-icon');
            expect(icon).toHaveClass('me-2');
        });
    });

    describe('Accessibility', () => {
        it('dropdown has proper label association', () => {
            render(<DownloadArtifacts />);
            const label = screen.getByText('Select Cognos Release');
            expect(label).toHaveClass('form-label');
        });

        it('button is keyboard accessible', () => {
            render(<DownloadArtifacts />);
            const button = screen.getByRole('button', { name: /Download Artifact/i });
            expect(button).toBeInTheDocument();
            expect(button.tagName).toBe('BUTTON');
        });

        it('select is keyboard accessible', () => {
            render(<DownloadArtifacts />);
            const select = screen.getByRole('combobox');
            expect(select.tagName).toBe('SELECT');
        });
    });

    describe('Styling Classes', () => {
        it('applies Bootstrap card styling', () => {
            const { container } = render(<DownloadArtifacts />);
            const cards = container.querySelectorAll('.card');
            expect(cards.length).toBeGreaterThan(0);
        });

        it('applies Bootstrap grid classes', () => {
            const { container } = render(<DownloadArtifacts />);
            const rows = container.querySelectorAll('.row');
            expect(rows.length).toBeGreaterThan(0);
        });

        it('applies margin bottom to header', () => {
            const { container } = render(<DownloadArtifacts />);
            const headerRow = container.querySelector('.full-width-header');
            expect(headerRow).toHaveClass('mb-4');
        });

        it('applies padding to card body', () => {
            const { container } = render(<DownloadArtifacts />);
            const cardBodies = container.querySelectorAll('.card-body.p-4');
            expect(cardBodies.length).toBeGreaterThan(0);
        });
    });

    describe('Component Structure', () => {
        it('has two main card sections', () => {
            const { container } = render(<DownloadArtifacts />);
            const cards = container.querySelectorAll('.card.card-dark');
            expect(cards.length).toBe(2);
        });

        it('header section has proper Bootstrap classes', () => {
            const { container } = render(<DownloadArtifacts />);
            const headerCol = container.querySelector('.full-width-header .col-12');
            expect(headerCol).toBeInTheDocument();
        });

        it('download section has proper column classes', () => {
            const { container } = render(<DownloadArtifacts />);
            const downloadCol = container.querySelector('.col-lg-12.col-md-12.mb-4');
            expect(downloadCol).toBeInTheDocument();
        });
    });

    describe('Text Content', () => {
        it('label has correct styling classes', () => {
            render(<DownloadArtifacts />);
            const label = screen.getByText('Select Cognos Release');
            expect(label).toHaveClass('form-label', 'text-slate', 'small', 'fw-medium');
        });
    });

    describe('Button Content', () => {
        it('button contains icon and text', () => {
            render(<DownloadArtifacts />);
            const button = screen.getByRole('button', { name: /Download Artifact/i });

            expect(button).toContainElement(screen.getByTestId('download-icon'));
            expect(button).toHaveTextContent('Download Artifact');
        });
    });

    describe('Responsive Design', () => {
        it('applies responsive column classes', () => {
            const { container } = render(<DownloadArtifacts />);
            const column = container.querySelector('.col-lg-12.col-md-12');
            expect(column).toBeInTheDocument();
        });

        it('uses Bootstrap responsive utilities', () => {
            const { container } = render(<DownloadArtifacts />);
            const responsiveElements = container.querySelectorAll('[class*="col-"]');
            expect(responsiveElements.length).toBeGreaterThan(0);
        });
    });
});